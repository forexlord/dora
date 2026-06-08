"""On-screen status card helpers for DoraAssistant."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from core import console_ui

if TYPE_CHECKING:
    from core.session import SessionState


class OverlayMixin:
    """Mixin methods expect a host implementing :class:`~core.assistant.protocol.AssistantHost`."""
    def _on_speech_pause_processing(self) -> None:
        if not self._show_processing_on_speech_pause or self._overlay_user_hidden:
            return
        self._overlay.show()
        self._set_overlay_phase(
            "thinking", "Got it — please pause so I can finish hearing you."
        )
        if self._echo_listen_status:
            console_ui.emit_dim("Processing…")

    def _after_command_captured(self) -> None:
        if self._overlay_user_hidden:
            return
        self._overlay.show()
        self._set_overlay_phase("thinking", "Working on that — one moment.")
        if self._echo_listen_status:
            console_ui.emit_dim("Processing…")

    def _announce_ready(self, begin_overlay_hidden: bool) -> None:
        """After boot (especially background), tell the user Dora is listening."""
        if not self._config.announce_ready_at_startup:
            return
        if self._listener is None:
            return
        msg = self._config.ready_message.strip()
        if not msg:
            msg = "Dora is ready. Say Dora or hey Dora when you need me."
        if begin_overlay_hidden and not self._overlay_user_hidden:
            self._overlay.show()
            self._set_overlay_phase("waiting_wake", msg)
        if self._echo_listen_status:
            console_ui.emit(msg, style="green")
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

    def _sync_overlay_for_session(self, state: SessionState) -> None:
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

    def _refresh_overlay_post_start(self, state: SessionState) -> None:
        if self._overlay_user_hidden:
            return
        if self._listener is None:
            self._set_overlay_phase("text_mode")
        elif self._wake_word_enabled and self._wake_phrases:
            self._set_overlay_phase("waiting_wake")
        else:
            self._set_overlay_phase("listening")

    def _overlay_before_listen(self, state: SessionState) -> None:
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

    def _overlay_after_response(self, state: SessionState) -> None:
        if self._listener is None:
            self._overlay.show()
            self._set_overlay_phase("text_mode")
            return
        if self._wake_word_enabled and self._wake_phrases:
            if time.time() <= state.wake_armed_until:
                self._overlay.show()
                self._set_overlay_phase(
                    "listening", "I'm still listening — go ahead when you're ready."
                )
            else:
                self._overlay.hide()
        else:
            self._overlay.show()
            self._set_overlay_phase("listening")

    def _speak_with_overlay(self, text: str, state: SessionState | None = None) -> None:
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
