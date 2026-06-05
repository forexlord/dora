"""Dora voice assistant — wires config, speech, TTS, and intent execution."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from core import console_ui
from core.assistant.mixins.dispatch import DispatchMixin
from core.assistant.mixins.input import InputMixin
from core.assistant.mixins.overlay import OverlayMixin
from core.assistant.mixins.startup import StartupMixin
from core.bootstrap import (
    config_use_llm_fallback,
    ensure_runtime_files,
    llm_model_path_from_config,
)
from core.config_helpers import (
    config_bool,
    config_float,
    config_get,
    config_int,
    config_optional_positive_int,
)
from core.executor import CommandExecutor
from core.intent import IntentParser
from core.listener import VoiceListener, WhisperVoiceListener
from core.llama_server import stop_llama_server
from core.paths import load_json, resolve_working_directory
from core.permissions import PermissionStore
from core.session import SessionState
from core.status_overlay import build_status_overlay
from core.tts import TextToSpeech
from core.wake_config import build_wake_prefix_aliases, parse_wake_phrases


class DoraAssistant(
    OverlayMixin,
    InputMixin,
    StartupMixin,
    DispatchMixin,
):
    """
    Main loop lives here so ``main.py`` / the ``dora`` console script stay thin.
    Behavior is split across mixins in ``core.assistant.mixins``.
    """

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
        self._use_llm = config_use_llm_fallback(config)
        self._allow_chat_fallback = config_bool(config, "allow_chat_fallback", default=True)
        llm_ctx = config_optional_positive_int(config, "llm_n_ctx", "ollama_num_ctx")
        self._parser = IntentParser(
            model_path=llm_model_path_from_config(config),
            config=config,
            use_llm_fallback=self._use_llm,
            num_predict_resolve=config_int(
                config, "llm_num_predict_resolve", "ollama_num_predict_resolve", default=56
            ),
            num_predict_chat=config_int(
                config, "llm_num_predict_chat", "ollama_num_predict_chat", default=72
            ),
            temperature_resolve=config_float(
                config, "llm_temperature_resolve", "ollama_temperature_resolve", default=0.0
            ),
            n_ctx=llm_ctx,
            n_threads=config_int(config, "llm_n_threads", default=0),
            fast_chat_path=config_bool(
                config, "llm_fast_chat_path", "ollama_fast_chat_path", default=True
            ),
            allow_chat=self._allow_chat_fallback,
        )
        self._tts = TextToSpeech(
            enabled=config_bool(config, "speak_responses", default=True),
            rate=config_int(config, "tts_rate", default=0),
            volume=config_int(config, "tts_volume", default=70),
            preferred_voice=str(config_get(config, "tts_voice", default="zira")),
        )
        self._executor = CommandExecutor(
            permission_store=self._permission_store,
            apps_dir=apps_dir,
            auto_discover_apps=config_bool(config, "auto_discover_apps", default=True),
            trust_mapped_apps=config_bool(config, "trust_mapped_apps", default=True),
        )
        self._listener: VoiceListener | WhisperVoiceListener | None = None
        self._wake_word_enabled = config_bool(config, "wake_word_enabled", default=True)
        self._wake_phrases, self._wake_hint = parse_wake_phrases(config)
        self._wake_prefix_alts = build_wake_prefix_aliases(self._wake_phrases, config)
        self._voice_session_after_wake_sec = config_int(
            config, "voice_session_after_wake_sec", "wake_word_timeout_sec", default=120
        )
        self._voice_processing_grace_sec = config_int(config, "voice_processing_grace_sec", default=180)
        self._post_response_listen_window_sec = config_int(
            config, "post_response_listen_window_sec", default=10
        )
        self._voice_idle_timeout_sec = config_float(config, "voice_idle_timeout_sec", default=10.0)
        self._text_fallback_enabled = config_bool(config, "allow_text_fallback", default=True)
        self._warmup_llm_on_start = config_bool(
            config, "warmup_llm_on_start", "warmup_ollama_on_start", default=True
        )
        self._llm_ready = False
        self._idle_rms_threshold = config_float(config, "vosk_idle_rms_threshold", default=550.0)
        self._echo_listen_status = not config_bool(config, "show_status_overlay", default=True)
        console_ui.configure(verbose_voice=self._echo_listen_status)
        self._show_processing_on_speech_pause = config_bool(
            config, "show_processing_on_speech_pause", default=True
        )
        self._speech_pause_to_processing_sec = config_float(
            config, "speech_pause_to_processing_sec", default=0.55
        )
        self._startup_complete = False
        self._overlay_user_hidden = False
        self._user_cancelled = False
        self._cancel_event = threading.Event()
        self._session: SessionState | None = None
        self._overlay = build_status_overlay(
            config_bool(config, "show_status_overlay", default=True),
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

    def run(self) -> None:
        self._overlay.start(begin_hidden=False)
        self._set_overlay_phase(
            "starting", "Starting — checking speech, microphone, and AI on this PC…"
        )
        if self._echo_listen_status:
            console_ui.emit_dim("Starting Dora…")
        self._run_environment_checks()
        self._maybe_index_apps()
        self._warmup_llm()
        self._init_listener()
        begin_overlay_hidden = self._overlay_hidden_until_wake()
        if begin_overlay_hidden:
            self._overlay.hide()
        console_ui.emit("Dora started (Ctrl+C to stop)", style="bold green")
        state = SessionState()
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
                    console_ui.emit("\nStopping Dora", style="bold")
                    break
                except Exception as exc:  # pragma: no cover
                    console_ui.emit(f"Error: {exc}", style="red")
        finally:
            self._session = None
            self._tts.stop()
            self._overlay.shutdown()
            stop_llama_server()


def run_assistant() -> None:
    """CLI entry: create default files, load JSON config, run Dora."""
    work = resolve_working_directory()
    try:
        os.chdir(work)
    except OSError as exc:
        console_ui.emit(f"Startup failed: cannot use data folder {work}: {exc}", style="bold red")
        return

    cfg_path = work / "config.json"
    if not cfg_path.is_file():
        console_ui.emit_markup(
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
        console_ui.emit(f"Startup failed: {exc}", style="bold red")
        return
    DoraAssistant(config, apps_dir=work / "apps").run()
