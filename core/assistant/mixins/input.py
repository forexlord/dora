"""Wake word gating and voice/text input acquisition."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from core import console_ui
from core.intent.rules import is_session_end_phrase
from core.session import (
    SESSION_END_TTS,
    clear_chat_context,
    heard_is_confirmation,
    heard_is_denial,
    heard_is_likely_prompt_echo,
)
from core.wake_config import match_wake_utterance, preprocess_wake_hearing

if TYPE_CHECKING:
    from core.session import SessionState


class InputMixin:
    """Mixin methods expect a host implementing :class:`~core.assistant.protocol.AssistantHost`."""
    def _normalize_wake_hearing(self, normalized: str) -> str:
        return preprocess_wake_hearing(
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
            waiting_for_wake = (
                self._wake_word_enabled
                and bool(self._wake_phrases)
                and not was_armed
            )
            self._overlay_before_listen(state)
            use_pause_cb = self._show_processing_on_speech_pause and (
                was_armed
                or not (self._wake_word_enabled and self._wake_phrases)
            )
            listen_rms = self._idle_rms_threshold
            if waiting_for_wake:
                listen_rms = self._idle_rms_threshold * self._wake_listen_rms_multiplier
            text = listener.listen_once(
                idle_timeout_sec=idle_to_use,
                echo_status=self._echo_listen_status and was_armed,
                idle_rms_threshold=listen_rms,
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
            raw_heard = text.strip()
            if self._config.show_heard_transcript and raw_heard:
                console_ui.emit_heard(raw_heard)
                if was_armed and not self._overlay_user_hidden:
                    self._overlay.show()
                    self._set_overlay_phase("thinking", f'Heard: "{raw_heard[:100]}"')
            normalized_text = " ".join(raw_heard.lower().split())
            if self._wake_word_enabled and self._wake_phrases:
                text = self._apply_wake_word_gate(raw_heard, normalized_text, state)
                if text is None:
                    if waiting_for_wake and not self._overlay_user_hidden:
                        self._overlay.hide()
                    return None
            self._after_command_captured(text)
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
        wake_match = match_wake_utterance(
            normalized_text, self._wake_phrases, self._wake_prefix_alts
        )

        if time.time() > state.wake_armed_until:
            if wake_match is None:
                return None
            if not wake_match.command_tail:
                self._on_wake_only(state)
                return None
            self._overlay_user_hidden = False
            self._overlay.show()
            state.wake_armed_until = time.time() + self._voice_processing_grace_sec
            return wake_match.command_tail
        if time.time() <= state.wake_armed_until:
            if wake_match is not None and not wake_match.command_tail:
                self._on_wake_only(state)
                return None
            if wake_match is not None and wake_match.command_tail:
                return wake_match.command_tail
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
            answer = input(f"{prompt} (yes/no): ").strip().lower()
            return heard_is_confirmation(answer)
        self._overlay.show()
        sub = prompt if len(prompt) <= 180 else prompt[:177] + "…"
        self._set_overlay_phase("confirm", sub)
        console_ui.emit(prompt, style="yellow")
        tts_thread = self._tts.speak_async(prompt, cancel_event=self._cancel_event)
        tts_stopped = False

        def stop_tts_on_voice() -> None:
            nonlocal tts_stopped
            if not tts_stopped:
                self._tts.stop()
                tts_stopped = True

        deadline = time.monotonic() + 18.0
        attempts = 0
        while time.monotonic() < deadline and attempts < 5:
            attempts += 1
            self._set_overlay_phase(
                "listening",
                "Yes, sure, or go ahead — anytime.",
            )
            heard = self._listener.listen_once(
                echo_status=attempts == 1 and self._echo_listen_status,
                idle_rms_threshold=self._idle_rms_threshold,
                on_speech_pause=self._on_speech_pause_processing
                if self._show_processing_on_speech_pause
                else None,
                speech_pause_to_processing_sec=self._speech_pause_to_processing_sec,
                cancel_event=self._cancel_event,
                on_voice_start=stop_tts_on_voice,
            )
            if self._user_cancelled:
                break
            if not heard.strip():
                continue
            console_ui.emit_voice(f"Heard confirmation: {heard}")
            if heard_is_likely_prompt_echo(heard, prompt):
                continue
            if heard_is_denial(heard):
                self._tts.stop()
                tts_thread.join(timeout=1.0)
                return False
            if heard_is_confirmation(heard):
                self._tts.stop()
                tts_thread.join(timeout=1.0)
                return True
        self._tts.stop()
        tts_thread.join(timeout=1.0)
        return False
