"""Wake word gating and voice/text input acquisition."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from core import console_ui
from core.intent.rules import is_session_end_phrase
from core.session import CONFIRM_HEARD, SESSION_END_TTS, clear_chat_context, heard_is_confirmation
from core.wake_config import normalize_wake_hearing

if TYPE_CHECKING:
    from core.session import SessionState


class InputMixin:
    """Mixin methods expect a host implementing :class:`~core.assistant.protocol.AssistantHost`."""
    def _normalize_wake_hearing(self, normalized: str) -> str:
        return normalize_wake_hearing(
            normalized, self._wake_phrases, self._wake_prefix_alts
        )

    def _acquire_user_text(self, state: SessionState) -> str | None:
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
                    console_ui.emit_dim(
                        "Session idle — no speech. "
                        "Say your wake word when you need me again."
                    )
                    self._overlay.hide()
                    self._tts.speak(SESSION_END_TTS, cancel_event=self._cancel_event)
                return None
            if self._user_cancelled:
                return None
            console_ui.emit_heard(text)
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
        state: SessionState,
    ) -> str | None:
        nt = self._normalize_wake_hearing(normalized_text)
        phrases = self._wake_phrases

        if time.time() > state.wake_armed_until:
            for phrase in phrases:
                if nt == phrase:
                    self._on_wake_only(state)
                    return None
                prefix = phrase + " "
                if nt.startswith(prefix):
                    tail = nt[len(prefix) :].strip()
                    if not tail:
                        self._on_wake_only(state)
                        return None
                    self._overlay_user_hidden = False
                    self._overlay.show()
                    state.wake_armed_until = time.time() + self._voice_processing_grace_sec
                    return tail
            return None
        if time.time() <= state.wake_armed_until:
            if any(nt == p for p in phrases):
                self._on_wake_only(state)
                return None
        if is_session_end_phrase(normalized_text):
            console_ui.emit_reply(SESSION_END_TTS)
            state.wake_armed_until = 0.0
            clear_chat_context(state)
            self._overlay.hide()
            self._tts.speak(SESSION_END_TTS, cancel_event=self._cancel_event)
            return None
        return text

    def _on_wake_only(self, state: SessionState) -> None:
        console_ui.emit_wake_detected()
        self._overlay_user_hidden = False
        self._overlay.show()
        self._set_overlay_phase("listening", "What would you like?")
        self._tts.speak("Yes?", cancel_event=self._cancel_event)
        state.wake_armed_until = time.time() + self._voice_session_after_wake_sec

    def _confirm_action(self, prompt: str) -> bool:
        if self._listener is None:
            answer = input(f"{prompt} (yes/confirm): ").strip().lower()
            return answer in CONFIRM_HEARD
        self._overlay.show()
        sub = prompt if len(prompt) <= 180 else prompt[:177] + "…"
        self._set_overlay_phase("confirm", sub)
        console_ui.emit(f"{prompt} Say 'yes' or 'confirm' anytime.", style="yellow")
        tts_thread = self._tts.speak_async(prompt, cancel_event=self._cancel_event)
        self._set_overlay_phase(
            "listening",
            "Say yes or confirm — you don't need to wait for me to finish.",
        )
        heard = self._listener.listen_once(
            echo_status=self._echo_listen_status,
            idle_rms_threshold=self._idle_rms_threshold,
            on_speech_pause=self._on_speech_pause_processing
            if self._show_processing_on_speech_pause
            else None,
            speech_pause_to_processing_sec=self._speech_pause_to_processing_sec,
            cancel_event=self._cancel_event,
        )
        self._tts.stop()
        tts_thread.join(timeout=1.0)
        if self._user_cancelled:
            return False
        console_ui.emit_voice(f"Heard confirmation: {heard}")
        return heard_is_confirmation(heard)
