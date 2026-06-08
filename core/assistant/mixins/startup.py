"""Startup checks: speech model, LLM, mic listener."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core import console_ui
from core.bootstrap import (
    ensure_llama_tools,
    ensure_llm_model,
    ensure_vosk_model,
    persist_config,
)
from core.listener import VoiceSetupError, create_speech_listener

if TYPE_CHECKING:
    pass


class StartupMixin:
    """Mixin methods expect a host implementing :class:`~core.assistant.protocol.AssistantHost`."""

    def _run_environment_checks(self) -> None:
        cfg = self._config
        cfg_dict = cfg.to_dict()
        if cfg.stt_engine.strip().lower() != "whisper":
            console_ui.emit("Checking local speech model...", style="cyan")
            model_ok, model_message, discovered_path = ensure_vosk_model(cfg_dict)
            style = "green" if model_ok else "yellow"
            console_ui.emit(model_message, style=style)
            if discovered_path and discovered_path != cfg.vosk_model_path:
                cfg.vosk_model_path = discovered_path
                persist_config(cfg.to_dict(), path=str(self._config_path))
                console_ui.emit(
                    f"Updated config vosk_model_path -> {discovered_path}", style="cyan"
                )
        else:
            console_ui.emit("Speech model: Whisper (Vosk download skipped).", style="cyan")

        if self._use_llm or self._allow_chat_fallback:
            console_ui.emit("Checking local AI tools (llama.cpp)...", style="cyan")
            tools_ok, tools_msg = ensure_llama_tools(cfg_dict)
            style = "green" if tools_ok else "yellow"
            console_ui.emit(tools_msg, style=style)
            console_ui.emit("Checking language model (GGUF)...", style="cyan")
            model_ready, model_status = ensure_llm_model(cfg_dict)
            style = "green" if model_ready else "yellow"
            console_ui.emit(model_status, style=style)

    def _maybe_index_apps(self) -> None:
        if not self._config.auto_discover_apps:
            return
        apps = (Path.cwd() / "apps").resolve()
        console_ui.emit_markup(
            "[cyan]Apps:[/cyan] Dora resolves names from Windows (Start Menu / installed apps) "
            f"and from shortcuts or executables in:\n  [bold]{apps}[/bold]\n"
            "[dim](.exe, .lnk, .bat, .cmd in that folder — add a shortcut to pin a custom name.)[/dim]"
        )

    def _warmup_llm(self) -> None:
        if not self._warmup_llm_on_start:
            return
        if not (self._allow_chat_fallback or self._use_llm):
            return
        console_ui.emit("Warming up local language model...", style="cyan")
        if self._parser.warmup_model():
            self._llm_ready = True
            console_ui.emit("Language model is ready.", style="green")
        else:
            self._llm_ready = False
            console_ui.emit("Model warmup skipped or failed; continuing.", style="yellow")
            err = self._parser.llm_load_error()
            if err:
                console_ui.emit(err, style="yellow")

    def _init_listener(self) -> None:
        try:
            self._listener = create_speech_listener(self._config)
            console_ui.emit(
                f"Speech recognition: {self._listener.engine_label}", style="cyan"
            )
        except VoiceSetupError as exc:
            if self._text_fallback_enabled:
                console_ui.emit(f"Voice setup unavailable: {exc}", style="yellow")
                console_ui.emit(
                    "Running in text mode fallback. "
                    "Type commands manually while LLM intent fallback remains active.",
                    style="yellow",
                )
            else:
                raise
