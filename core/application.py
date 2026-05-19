"""Application entry: startup checks and Dora's main voice / text command loop."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from rich import print

from core.bootstrap import (
    ensure_ollama_model,
    ensure_ollama_runtime,
    ensure_runtime_files,
    ensure_vosk_model,
    persist_config,
)
from core.executor import CommandExecutor
from core.intent import DEFAULT_VOLUME_STEP_PERCENT, IntentParser
from core.intent.rules import is_session_end_phrase
from core.listener import (
    VoiceListener,
    WhisperVoiceListener,
    VoiceSetupError,
    create_speech_listener,
)
from core.permissions import PermissionStore
from core.status_overlay import build_status_overlay
from core.system_actions import apply_system_intent
from core.system_intents import is_system_intent
from core.tts import TextToSpeech


def load_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return json.loads(file_path.read_text(encoding="utf-8"))


def resolve_working_directory() -> Path:
    """
    Where config.json, models/, permissions, and the optional ``apps/`` folder live.

    Set DORA_HOME to that folder (recommended after pip install).
    VOICE_ASSISTANT_HOME is still accepted if DORA_HOME is unset.
    If both unset, the current working directory is used.
    """
    raw = (
        os.environ.get("DORA_HOME", "").strip()
        or os.environ.get("VOICE_ASSISTANT_HOME", "").strip()
    )
    if raw:
        root = Path(raw).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root
    return Path.cwd().resolve()


def parse_wake_phrases(config: dict[str, Any]) -> tuple[list[str], str]:
    """
    Build wake phrases (longest first for prefix matching) and overlay/TTS hint text.
    If wake_phrases is set in config, use it; else wake_word plus dora/hey-dora pairing.
    """
    raw = config.get("wake_phrases")
    phrases: list[str] = []
    if isinstance(raw, list) and raw:
        phrases = [" ".join(str(x).lower().split()) for x in raw if str(x).strip()]
    else:
        w = str(config.get("wake_word", "dora")).strip().lower() or "dora"
        phrases = [w]
        if w in {"dora", "hey dora"} or w.endswith(" dora"):
            if "dora" not in phrases:
                phrases.append("dora")
            if "hey dora" not in phrases:
                phrases.append("hey dora")
    phrases = [p for p in phrases if p.strip()]
    if not phrases:
        phrases = ["dora", "hey dora"]
    phrases = sorted(set(phrases), key=len, reverse=True)

    hint = str(config.get("wake_hint", "")).strip()
    if not hint and phrases:
        short_first = sorted(phrases, key=len)
        parts = [f"“{p}”" for p in short_first]
        hint = "Say " + " or ".join(parts) + " when you need me."
    elif not hint:
        hint = "Say the wake phrase when you need me."
    return phrases, hint


@dataclass
class _SessionState:
    wake_armed_until: float = 0.0
    pending_followup: dict[str, str] | None = None
    chat_context: dict[str, str] | None = None


# First word of the wake phrase is often mis-heard (hey → a, oh, uh…).
_DEFAULT_WAKE_PREFIX_ALIASES: frozenset[str] = frozenset(
    {
        "hey",
        "hi",
        "ah",
        "a",
        "oh",
        "uh",
        "um",
        "yo",
        "so",
        "well",
        "the",
        "ho",
        "huh",
        "haw",
        "hay",
    }
)


class DoraAssistant:
    """
    Wires config, speech, TTS, permissions, and intent execution.
    The main loop lives here so `main.py` / the `dora` console script stay thin.
    """

    _SESSION_END_TTS = "Call again when you need me."

    def __init__(
        self,
        config: dict[str, Any],
        *,
        config_path: str | Path = "config.json",
        apps_dir: str | Path = "apps",
    ) -> None:
        self._config = config
        self._config_path = Path(config_path)
        self._permission_store = PermissionStore("permissions.json")
        self._use_ollama = bool(config.get("use_ollama_fallback", True))
        self._allow_chat_fallback = bool(config.get("allow_chat_fallback", True))
        _nc = config.get("ollama_num_ctx")
        try:
            _cv = int(_nc) if _nc is not None and str(_nc).strip() != "" else None
        except (TypeError, ValueError):
            _cv = None
        _ollama_ctx = _cv if (_cv is not None and _cv > 0) else None
        _chat_model = str(config.get("ollama_chat_model", "")).strip() or None
        self._parser = IntentParser(
            ollama_model=config.get("ollama_model", "phi"),
            use_ollama_fallback=self._use_ollama,
            ollama_num_predict_resolve=int(config.get("ollama_num_predict_resolve", 56)),
            ollama_num_predict_chat=int(config.get("ollama_num_predict_chat", 72)),
            ollama_temperature_resolve=float(config.get("ollama_temperature_resolve", 0.0)),
            ollama_num_ctx=_ollama_ctx,
            ollama_chat_model=_chat_model,
            fast_chat_path=bool(config.get("ollama_fast_chat_path", True)),
            allow_chat=self._allow_chat_fallback,
        )
        self._tts = TextToSpeech(
            enabled=bool(config.get("speak_responses", True)),
            rate=int(config.get("tts_rate", 0)),
            volume=int(config.get("tts_volume", 70)),
            preferred_voice=str(config.get("tts_voice", "zira")),
        )
        self._executor = CommandExecutor(
            permission_store=self._permission_store,
            apps_dir=apps_dir,
            auto_discover_apps=bool(config.get("auto_discover_apps", True)),
            trust_mapped_apps=bool(config.get("trust_mapped_apps", True)),
        )
        self._listener: VoiceListener | WhisperVoiceListener | None = None
        self._wake_word_enabled = bool(config.get("wake_word_enabled", True))
        self._wake_phrases, self._wake_hint = parse_wake_phrases(config)
        _pfx = set(_DEFAULT_WAKE_PREFIX_ALIASES)
        for _p in self._wake_phrases:
            _toks = _p.split()
            if _toks:
                _pfx.add(_toks[0])
        _extra = config.get("wake_prefix_aliases")
        if isinstance(_extra, list):
            _pfx |= {str(x).lower().strip() for x in _extra if str(x).strip()}
        self._wake_prefix_alts: frozenset[str] = frozenset(_pfx)
        self._voice_session_after_wake_sec = int(
            config.get("voice_session_after_wake_sec", config.get("wake_word_timeout_sec", 120))
        )
        self._voice_processing_grace_sec = int(config.get("voice_processing_grace_sec", 180))
        self._post_response_listen_window_sec = int(config.get("post_response_listen_window_sec", 10))
        self._voice_idle_timeout_sec = float(config.get("voice_idle_timeout_sec", 10))
        self._text_fallback_enabled = bool(config.get("allow_text_fallback", True))
        self._warmup_ollama_on_start = bool(config.get("warmup_ollama_on_start", True))
        self._idle_rms_threshold = float(config.get("vosk_idle_rms_threshold", 550.0))
        self._echo_listen_status = not bool(config.get("show_status_overlay", True))
        self._show_processing_on_speech_pause = bool(
            config.get("show_processing_on_speech_pause", True)
        )
        self._speech_pause_to_processing_sec = float(
            config.get("speech_pause_to_processing_sec", 0.55)
        )
        self._startup_complete = False
        self._overlay_user_hidden = False
        self._user_cancelled = False
        self._cancel_event = threading.Event()
        self._session: _SessionState | None = None
        self._overlay = build_status_overlay(
            bool(config.get("show_status_overlay", True)),
            self._wake_hint,
            on_user_dismiss=self._on_overlay_user_dismiss,
        )

    def _on_overlay_user_dismiss(self) -> None:
        """User closed the status card (X). Startup keeps running hidden; else cancel work."""
        self._overlay_user_hidden = True
        if not self._startup_complete:
            return
        self._user_cancelled = True
        self._cancel_event.set()
        self._tts.stop()
        sess = self._session
        if sess is not None:
            sess.wake_armed_until = 0.0
            sess.pending_followup = None
            sess.chat_context = None

    def _remember_chat_turn(
        self, state: _SessionState, user_text: str, assistant_text: str
    ) -> None:
        reply = (assistant_text or "").strip()
        if not reply:
            return
        state.chat_context = {
            "user": " ".join(user_text.strip().split()),
            "assistant": reply,
        }

    def _build_chat_followup_context(
        self, state: _SessionState, current_text: str
    ) -> str | None:
        ctx = state.chat_context
        if not ctx or not str(ctx.get("assistant", "")).strip():
            return None
        return (
            "Context: Continue the same voice conversation.\n"
            f"Dora last said: {ctx['assistant']}\n"
            f"User previously said: {ctx.get('user', '')}\n"
            f"User now says: {' '.join(current_text.strip().split())}\n"
            "Reply naturally as a follow-up to what you just said."
        )

    def _clear_chat_context(self, state: _SessionState) -> None:
        state.chat_context = None

    def _rewrite_alias_to_two_word_phrase(
        self, normalized: str, w0: str, name: str, canonical: str
    ) -> str:
        """STT: a dora / oh dora → canonical two-word phrase (e.g. hey dora)."""
        if normalized == canonical or normalized.startswith(canonical + " "):
            return normalized
        toks = normalized.split()
        if len(toks) < 2:
            return normalized
        t0 = toks[0].rstrip(".,!?")
        t1 = toks[1].rstrip(".,!?")
        if t1 != name.rstrip(".,!?"):
            return normalized
        if t0 not in self._wake_prefix_alts and t0 != w0:
            return normalized
        rest = toks[2:]
        return f"{canonical} {' '.join(rest)}".rstrip() if rest else canonical

    def _rewrite_alias_to_single_name(self, normalized: str, name: str) -> str:
        """STT: a dora → dora when single-word wake is configured."""
        if normalized == name or normalized.startswith(name + " "):
            return normalized
        toks = normalized.split()
        if len(toks) < 2:
            return normalized
        t0 = toks[0].rstrip(".,!?")
        t1 = toks[1].rstrip(".,!?")
        if t1 != name.rstrip(".,!?"):
            return normalized
        if t0 not in self._wake_prefix_alts:
            return normalized
        rest = toks[2:]
        return f"{name} {' '.join(rest)}".rstrip() if rest else name

    def _normalize_wake_hearing(self, normalized: str) -> str:
        nt = normalized
        for p in self._wake_phrases:
            parts = p.split()
            if len(parts) == 2:
                nt = self._rewrite_alias_to_two_word_phrase(nt, parts[0], parts[1], p)
        for p in self._wake_phrases:
            if " " not in p:
                nt = self._rewrite_alias_to_single_name(nt, p)
        return nt

    def _on_speech_pause_processing(self) -> None:
        if not self._show_processing_on_speech_pause or self._overlay_user_hidden:
            return
        self._overlay.show()
        self._set_overlay_phase(
            "thinking", "Got it — please pause so I can finish hearing you."
        )
        if self._echo_listen_status:
            print("[dim]Processing…[/dim]", flush=True)

    def _after_command_captured(self) -> None:
        if self._overlay_user_hidden:
            return
        self._overlay.show()
        self._set_overlay_phase("thinking", "Working on that — one moment.")
        if self._echo_listen_status:
            print("[dim]Processing…[/dim]", flush=True)

    # --- lifecycle ---------------------------------------------------------

    def run(self) -> None:
        self._overlay.start(begin_hidden=False)
        self._set_overlay_phase(
            "starting", "Starting — checking speech, microphone, and AI on this PC…"
        )
        if self._echo_listen_status:
            print("[dim]Starting Dora…[/dim]", flush=True)
        self._run_environment_checks()
        self._maybe_index_apps()
        self._warmup_llm()
        self._init_listener()
        begin_overlay_hidden = self._overlay_hidden_until_wake()
        if begin_overlay_hidden:
            self._overlay.hide()
        print("[bold green]Dora started (Ctrl+C to stop)[/bold green]")
        state = _SessionState()
        self._session = state
        if not begin_overlay_hidden:
            self._refresh_overlay_post_start(state)
        self._announce_ready(begin_overlay_hidden)
        self._startup_complete = True
        try:
            while True:
                try:
                    text = self._acquire_user_text(state)
                    if text is None:
                        continue
                    self._dispatch_turn(text, state)
                except KeyboardInterrupt:
                    print("\n[bold]Stopping Dora[/bold]")
                    break
                except Exception as exc:  # pragma: no cover
                    print(f"[red]Error:[/red] {exc}")
        finally:
            self._session = None
            self._overlay.shutdown()

    def _run_environment_checks(self) -> None:
        cfg = self._config
        if str(cfg.get("stt_engine", "vosk")).strip().lower() != "whisper":
            print("[cyan]Checking local speech model...[/cyan]")
            model_ok, model_message, discovered_path = ensure_vosk_model(cfg)
            style = "green" if model_ok else "yellow"
            print(f"[{style}]{model_message}[/{style}]")
            if discovered_path and discovered_path != cfg.get("vosk_model_path"):
                cfg["vosk_model_path"] = discovered_path
                persist_config(cfg, path=str(self._config_path))
                print(f"[cyan]Updated config vosk_model_path -> {discovered_path}[/cyan]")
        else:
            print("[cyan]Speech model:[/cyan] Whisper (Vosk download skipped).")

        if self._use_ollama or self._allow_chat_fallback:
            print("[cyan]Checking local Ollama runtime...[/cyan]")
            ollama_ok, ollama_message = ensure_ollama_runtime(cfg)
            style = "green" if ollama_ok else "yellow"
            print(f"[{style}]{ollama_message}[/{style}]")
            if ollama_ok:
                model_ready, model_status = ensure_ollama_model(cfg)
                style = "green" if model_ready else "yellow"
                print(f"[{style}]{model_status}[/{style}]")

    def _maybe_index_apps(self) -> None:
        if not bool(self._config.get("auto_discover_apps", True)):
            return
        apps = (Path.cwd() / "apps").resolve()
        print(
            "[cyan]Apps:[/cyan] Dora resolves names from Windows (Start Menu / installed apps) "
            f"and from shortcuts or executables in:\n  [bold]{apps}[/bold]\n"
            "[dim](.exe, .lnk, .bat, .cmd in that folder — add a shortcut to pin a custom name.)[/dim]"
        )

    def _warmup_llm(self) -> None:
        if not self._warmup_ollama_on_start:
            return
        if not (self._allow_chat_fallback or self._config.get("use_ollama_fallback", True)):
            return
        print("[cyan]Warming up local Ollama model...[/cyan]")
        if self._parser.warmup_model():
            print("[green]Ollama model is ready.[/green]")
        else:
            print("[yellow]Ollama warmup skipped or failed; continuing.[/yellow]")

    def _init_listener(self) -> None:
        cfg = self._config
        try:
            self._listener = create_speech_listener(cfg)
            print(f"[cyan]Speech recognition:[/cyan] {self._listener.engine_label}")
        except VoiceSetupError as exc:
            if self._text_fallback_enabled:
                print(f"[yellow]Voice setup unavailable:[/yellow] {exc}")
                print(
                    "[yellow]Running in text mode fallback. "
                    "Type commands manually while Ollama intent fallback remains active.[/yellow]"
                )
            else:
                raise

    # --- status overlay (Siri-like on-screen feedback) --------------------

    def _announce_ready(self, begin_overlay_hidden: bool) -> None:
        """After boot (especially background), tell the user Dora is listening."""
        if not bool(self._config.get("announce_ready_at_startup", True)):
            return
        if self._listener is None:
            return
        msg = str(self._config.get("ready_message", "")).strip()
        if not msg:
            msg = "Dora is ready. Say Dora or hey Dora when you need me."
        if begin_overlay_hidden and not self._overlay_user_hidden:
            self._overlay.show()
            self._set_overlay_phase("waiting_wake", msg)
        print(f"[green]{msg}[/green]")
        self._tts.speak(msg, cancel_event=self._cancel_event)
        if begin_overlay_hidden and not self._overlay_user_hidden:
            self._overlay.hide()

    def _overlay_hidden_until_wake(self) -> bool:
        """When True, status window stays off until the wake word opens a session."""
        return (
            self._listener is not None
            and self._wake_word_enabled
            and bool(self._wake_phrases)
        )

    def _set_overlay_phase(self, phase: str, subtitle: str | None = None) -> None:
        self._overlay.set_phase(phase, subtitle)

    def _sync_overlay_for_session(self, state: _SessionState) -> None:
        """Show the card only while a wake session is active (or when wake is off)."""
        if self._listener is None:
            self._overlay.show()
            return
        if not self._wake_word_enabled or not self._wake_phrases:
            self._overlay.show()
            return
        if time.time() <= state.wake_armed_until:
            self._overlay.show()
        else:
            self._overlay.hide()

    def _refresh_overlay_post_start(self, state: _SessionState) -> None:
        if self._overlay_user_hidden:
            return
        if self._listener is None:
            self._set_overlay_phase("text_mode")
        elif self._wake_word_enabled and self._wake_phrases:
            self._set_overlay_phase("waiting_wake")
        else:
            self._set_overlay_phase("listening")

    def _overlay_before_listen(self, state: _SessionState) -> None:
        if self._overlay_user_hidden:
            return
        if self._listener is None:
            self._overlay.show()
            self._set_overlay_phase("text_mode")
            return
        now = time.time()
        armed = (
            self._wake_word_enabled
            and bool(self._wake_phrases)
            and now <= state.wake_armed_until
        )
        if self._wake_word_enabled and self._wake_phrases and not armed:
            self._overlay.hide()
            return
        self._overlay.show()
        self._set_overlay_phase("listening")

    def _overlay_after_response(self, state: _SessionState) -> None:
        if self._listener is None:
            self._overlay.show()
            self._set_overlay_phase("text_mode")
            return
        if self._wake_word_enabled and self._wake_phrases:
            if time.time() <= state.wake_armed_until:
                self._overlay.show()
                self._set_overlay_phase("listening", "I'm still listening — go ahead when you're ready.")
            else:
                self._overlay.hide()
        else:
            self._overlay.show()
            self._set_overlay_phase("listening")

    def _speak_with_overlay(self, text: str, state: _SessionState | None = None) -> None:
        if self._user_cancelled:
            return
        if not self._overlay_user_hidden:
            self._overlay.show()
            self._set_overlay_phase("speaking")
        self._tts.speak(text, cancel_event=self._cancel_event)
        if self._user_cancelled:
            return
        if state is not None:
            self._overlay_after_response(state)
        elif self._listener is None:
            self._overlay.show()
            self._set_overlay_phase("text_mode")
        else:
            if self._wake_word_enabled and self._wake_phrases:
                self._overlay.hide()
            else:
                self._overlay.show()
                self._set_overlay_phase("listening")

    # --- input --------------------------------------------------------------

    def _acquire_user_text(self, state: _SessionState) -> str | None:
        self._user_cancelled = False
        self._cancel_event.clear()
        listener = self._listener
        if listener is not None:
            was_armed = (
                self._wake_word_enabled
                and bool(self._wake_phrases)
                and time.time() <= state.wake_armed_until
            )
            if was_armed:
                state.wake_armed_until = time.time() + self._voice_processing_grace_sec
            idle_to_use = self._voice_idle_timeout_sec if was_armed else None
            self._overlay_before_listen(state)
            use_pause_cb = self._show_processing_on_speech_pause and (
                was_armed
                or not (self._wake_word_enabled and self._wake_phrases)
            )
            text = listener.listen_once(
                idle_timeout_sec=idle_to_use,
                echo_status=self._echo_listen_status,
                idle_rms_threshold=self._idle_rms_threshold,
                on_speech_pause=self._on_speech_pause_processing if use_pause_cb else None,
                speech_pause_to_processing_sec=self._speech_pause_to_processing_sec,
                cancel_event=self._cancel_event,
            )
            if self._user_cancelled:
                self._cancel_event.clear()
                state.wake_armed_until = 0.0
                state.pending_followup = None
                return None
            if not text.strip():
                if was_armed:
                    state.wake_armed_until = 0.0
                    print(
                        "[dim]Session idle — no speech. "
                        "Say your wake word when you need me again.[/dim]"
                    )
                    self._overlay.hide()
                    self._tts.speak(
                        self._SESSION_END_TTS, cancel_event=self._cancel_event
                    )
                return None
            if self._user_cancelled:
                return None
            print(f"[cyan]Heard:[/cyan] {text}")
            normalized_text = " ".join(text.lower().strip().split())
            if self._wake_word_enabled and self._wake_phrases:
                text = self._apply_wake_word_gate(text, normalized_text, state)
                if text is None:
                    return None
            self._after_command_captured()
            return text

        self._set_overlay_phase("text_mode")
        raw = input("Command> ").strip()
        return raw or None

    def _apply_wake_word_gate(
        self,
        text: str,
        normalized_text: str,
        state: _SessionState,
    ) -> str | None:
        nt = self._normalize_wake_hearing(normalized_text)
        phrases = self._wake_phrases

        if time.time() > state.wake_armed_until:
            for p in phrases:
                if nt == p:
                    print("[cyan]Wake word detected. Listening for command...[/cyan]")
                    self._overlay_user_hidden = False
                    self._overlay.show()
                    self._set_overlay_phase("listening", "What would you like?")
                    self._tts.speak("Yes?", cancel_event=self._cancel_event)
                    state.wake_armed_until = time.time() + self._voice_session_after_wake_sec
                    return None
                pref = p + " "
                if nt.startswith(pref):
                    tail = nt[len(pref) :].strip()
                    if not tail:
                        print("[cyan]Wake word detected. Listening for command...[/cyan]")
                        self._overlay_user_hidden = False
                        self._overlay.show()
                        self._set_overlay_phase("listening", "What would you like?")
                        self._tts.speak("Yes?", cancel_event=self._cancel_event)
                        state.wake_armed_until = time.time() + self._voice_session_after_wake_sec
                        return None
                    self._overlay_user_hidden = False
                    self._overlay.show()
                    state.wake_armed_until = time.time() + self._voice_processing_grace_sec
                    return tail
            return None
        if time.time() <= state.wake_armed_until:
            if any(nt == p for p in phrases):
                print("[cyan]Still listening.[/cyan]")
                self._overlay_user_hidden = False
                self._overlay.show()
                self._set_overlay_phase("listening", "What would you like?")
                self._tts.speak("Yes?", cancel_event=self._cancel_event)
                state.wake_armed_until = time.time() + self._voice_session_after_wake_sec
                return None
        if is_session_end_phrase(normalized_text):
            print(f"[magenta]Dora:[/magenta] {self._SESSION_END_TTS}")
            state.wake_armed_until = 0.0
            self._clear_chat_context(state)
            self._overlay.hide()
            self._tts.speak(self._SESSION_END_TTS, cancel_event=self._cancel_event)
            return None
        return text

    def _confirm_action(self, prompt: str) -> bool:
        if self._listener is None:
            answer = input(f"{prompt} (yes/confirm): ").strip().lower()
            return answer in {"yes", "confirm"}
        self._overlay.show()
        sub = prompt if len(prompt) <= 180 else prompt[:177] + "…"
        self._set_overlay_phase("confirm", sub)
        print(f"[yellow]{prompt} Say 'yes' or 'confirm'.[/yellow]")
        self._tts.speak(prompt, cancel_event=self._cancel_event)
        if self._user_cancelled:
            return False
        self._set_overlay_phase("listening", "Say yes or confirm out loud.")
        heard = self._listener.listen_once(
            echo_status=self._echo_listen_status,
            idle_rms_threshold=self._idle_rms_threshold,
            on_speech_pause=self._on_speech_pause_processing
            if self._show_processing_on_speech_pause
            else None,
            speech_pause_to_processing_sec=self._speech_pause_to_processing_sec,
            cancel_event=self._cancel_event,
        )
        if self._user_cancelled:
            return False
        print(f"[cyan]Heard confirmation:[/cyan] {heard}")
        normalized = " ".join(heard.lower().strip().split())
        return normalized in {"yes", "confirm"}

    # --- intent handling ----------------------------------------------------

    def _build_followup_context(self, pending: dict[str, str]) -> str:
        return (
            "Context: Follow-up to your previous clarification question. "
            f"Topic: {pending['pending']}. "
            f"You asked the user: {pending['reply']!r}. "
            "The PC already knows current volume/brightness—never ask the user for the current level. "
            "Parse their answer into the correct system JSON with numbers. "
            "Map: a little ~5, a lot ~20, bit ~5, max -> volume_set or brightness_set 100, "
            "minimum -> 0 or mute. "
            f"If they still only say 'increase' or 'louder' with no amount, "
            f"use volume_relative +{int(DEFAULT_VOLUME_STEP_PERCENT)}."
        )

    def _dispatch_turn(self, text: str, state: _SessionState) -> None:
        if self._user_cancelled:
            return
        self._sync_overlay_for_session(state)

        def before_llm() -> None:
            print("[dim]Thinking…[/dim]", flush=True)
            if not self._overlay_user_hidden:
                self._overlay.show()
                self._set_overlay_phase("thinking")

        follow_ctx = (
            self._build_followup_context(state.pending_followup)
            if state.pending_followup is not None
            else None
        )
        chat_ctx = (
            None
            if state.pending_followup is not None
            else self._build_chat_followup_context(state, text)
        )
        intent = self._parser.parse(
            text,
            on_before_llm=before_llm if self._use_ollama else None,
            follow_up_context=follow_ctx,
            chat_followup_context=chat_ctx,
        )
        if self._user_cancelled:
            state.pending_followup = None
            return
        intent_type = intent.get("type")
        extend = self._extend_wake_after_response

        if intent_type == "open":
            state.pending_followup = None
            self._clear_chat_context(state)
            ok, message = self._executor.open_app(intent.get("app", ""), confirm_fn=self._confirm_action)
            self._print_result(message, "green" if ok else "yellow")
            self._speak_with_overlay(message, state)
            extend(state)
        elif intent_type == "close":
            state.pending_followup = None
            self._clear_chat_context(state)
            ok, message = self._executor.close_app(
                intent.get("app", ""),
                force=bool(intent.get("force", False)),
                confirm_fn=self._confirm_action,
            )
            self._print_result(message, "green" if ok else "yellow")
            self._speak_with_overlay(message, state)
            extend(state)
        elif intent_type == "shutdown":
            state.pending_followup = None
            self._clear_chat_context(state)
            ok, message = self._executor.shutdown(
                require_confirmation=bool(self._config.get("confirm_shutdown", True)),
                confirm_fn=self._confirm_action,
            )
            self._print_result(message, "red" if ok else "yellow")
            self._speak_with_overlay(message, state)
            extend(state)
        elif is_system_intent(str(intent_type)):
            state.pending_followup = None
            self._clear_chat_context(state)
            ok, message = apply_system_intent(intent)
            self._print_result(message, "green" if ok else "yellow")
            self._speak_with_overlay(message, state)
            extend(state)
        elif intent_type == "clarify":
            self._handle_clarify(intent, state, extend)
        elif intent_type == "chat":
            state.pending_followup = None
            reply = str(intent.get("reply", "")).strip()
            if reply:
                print(f"[magenta]Dora:[/magenta] {reply}")
                self._speak_with_overlay(reply, state)
                self._remember_chat_turn(state, text, reply)
                extend(state)
            else:
                state.pending_followup = None
                self._cant_help(extend, state)
        elif intent_type == "confirm":
            return
        else:
            state.pending_followup = None
            reply = None
            if self._allow_chat_fallback and intent_type == "unknown":
                if self._use_ollama:
                    print("[dim]Thinking…[/dim]", flush=True)
                    self._set_overlay_phase("thinking")
                payload = text
                if chat_ctx:
                    payload = f"{chat_ctx}\n\nUser said: {text}"
                reply = self._parser.chat_reply(payload)
            if reply:
                print(f"[magenta]Dora:[/magenta] {reply}")
                self._speak_with_overlay(reply, state)
                self._remember_chat_turn(state, text, reply)
                extend(state)
                return
            self._cant_help(extend, state)

    def _handle_clarify(
        self,
        intent: dict[str, Any],
        state: _SessionState,
        extend: Callable[[_SessionState], None],
    ) -> None:
        reply = str(intent.get("reply", "")).strip()
        pending = str(intent.get("pending", "volume")).strip().lower()
        if pending not in VALID_CLARIFY_PENDING:
            pending = "volume"
        if reply:
            print(f"[magenta]Dora:[/magenta] {reply}")
            self._speak_with_overlay(reply, state)
            state.pending_followup = {"reply": reply, "pending": pending}
            self._remember_chat_turn(state, "", reply)
            extend(state)
        else:
            state.pending_followup = None
            print("[yellow]I need a bit more detail for that.[/yellow]")
            self._speak_with_overlay("I need a bit more detail for that.", state)
            extend(state)

    def _cant_help(self, extend: Callable[[_SessionState], None], state: _SessionState) -> None:
        print("[yellow]I can't help with that command.[/yellow]")
        self._speak_with_overlay("I can't help with that command.", state)
        extend(state)

    @staticmethod
    def _print_result(message: str, style: str) -> None:
        print(f"[{style}]{message}[/{style}]")

    def _extend_wake_after_response(self, state: _SessionState) -> None:
        if self._listener is not None and self._wake_word_enabled:
            state.wake_armed_until = time.time() + self._post_response_listen_window_sec


def run_assistant() -> None:
    """CLI entry: create default files, load JSON config, run Dora."""
    work = resolve_working_directory()
    try:
        os.chdir(work)
    except OSError as exc:
        print(f"[bold red]Startup failed:[/bold red] cannot use data folder {work}: {exc}")
        return

    cfg_path = work / "config.json"
    if not cfg_path.is_file():
        print(
            f"[bold red]Missing config.json[/bold red] in:\n  {work}\n\n"
            "Set environment variable [cyan]DORA_HOME[/cyan] to the folder that contains "
            "config.json, your [cyan]models[/cyan] directory, and optional [cyan]apps[/cyan] "
            "(your project folder), then run again.\n"
            "Example (PowerShell): "
            "[dim]$env:DORA_HOME='C:/Users/you/Documents/projects/voice-assistant'[/dim]"
        )
        return

    ensure_runtime_files()
    try:
        config = load_json("config.json")
    except Exception as exc:
        print(f"[bold red]Startup failed:[/bold red] {exc}")
        return
    DoraAssistant(config, apps_dir=work / "apps").run()
