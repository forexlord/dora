"""Parse intents and run executor / chat replies."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from core import console_ui
from core.intent import DEFAULT_VOLUME_STEP_PERCENT
from core.intent.constants import VALID_CLARIFY_PENDING
from core.intent.rules import ACTION_VERB_RE
from core.intent.safety import strip_dialogue_markup
from core.session import (
    build_chat_followup_context,
    clear_chat_context,
    remember_chat_turn,
)
from core.system_actions import apply_system_intent
from core.system_intents import is_system_intent

if TYPE_CHECKING:
    from core.session import SessionState


class DispatchMixin:
    """Mixin methods expect a host implementing :class:`~core.assistant.protocol.AssistantHost`."""
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

    def _dispatch_turn(self, text: str, state: SessionState) -> None:
        if self._user_cancelled:
            return
        self._sync_overlay_for_session(state)

        def before_llm() -> None:
            console_ui.emit_thinking()
            if not self._overlay_user_hidden:
                self._overlay.show()
                self._set_overlay_phase("thinking")

        follow_ctx = (
            self._build_followup_context(state.pending_followup)
            if state.pending_followup is not None
            else None
        )
        norm = " ".join(strip_dialogue_markup(text).lower().split())
        if ACTION_VERB_RE.search(norm):
            clear_chat_context(state)
        chat_ctx = (
            None
            if state.pending_followup is not None or ACTION_VERB_RE.search(norm)
            else build_chat_followup_context(
                state, text, max_turns=self._config.chat_memory_turns
            )
        )
        intent = self._parser.parse(
            text,
            on_before_llm=before_llm if self._use_llm else None,
            follow_up_context=follow_ctx,
            chat_followup_context=chat_ctx,
        )
        if self._user_cancelled:
            state.pending_followup = None
            return
        intent_type = intent.get("type")
        extend = self._extend_wake_after_response

        if intent_type == "open":
            self._run_app_action(state, extend, self._executor.open_app, intent, "app")
        elif intent_type == "close":
            self._run_close_action(state, extend, intent)
        elif intent_type == "shutdown":
            state.pending_followup = None
            clear_chat_context(state)
            ok, message = self._executor.shutdown(
                require_confirmation=self._config.confirm_shutdown,
                confirm_fn=self._confirm_action,
            )
            self._print_result(message, "red" if ok else "yellow")
            self._speak_with_overlay(message, state)
            extend(state)
        elif is_system_intent(str(intent_type)):
            state.pending_followup = None
            clear_chat_context(state)
            ok, message = apply_system_intent(intent)
            self._print_result(message, "green" if ok else "yellow")
            self._speak_with_overlay(message, state)
            extend(state)
        elif intent_type == "clarify":
            self._handle_clarify(intent, state, extend)
        elif intent_type == "chat":
            self._handle_chat(text, state, extend, str(intent.get("reply", "")).strip())
        elif intent_type == "confirm":
            return
        else:
            self._handle_unknown(text, state, extend, chat_ctx, str(intent_type))

    def _run_app_action(
        self,
        state: SessionState,
        extend: Callable[[SessionState], None],
        open_fn: Callable[..., tuple[bool, str]],
        intent: dict[str, Any],
        app_key: str,
    ) -> None:
        state.pending_followup = None
        clear_chat_context(state)
        ok, message = open_fn(intent.get(app_key, ""), confirm_fn=self._confirm_action)
        self._print_result(message, "green" if ok else "yellow")
        self._speak_with_overlay(message, state)
        extend(state)

    def _run_close_action(
        self,
        state: SessionState,
        extend: Callable[[SessionState], None],
        intent: dict[str, Any],
    ) -> None:
        state.pending_followup = None
        clear_chat_context(state)
        ok, message = self._executor.close_app(
            intent.get("app", ""),
            force=bool(intent.get("force", False)),
            confirm_fn=self._confirm_action,
        )
        self._print_result(message, "green" if ok else "yellow")
        self._speak_with_overlay(message, state)
        extend(state)

    def _handle_chat(
        self,
        text: str,
        state: SessionState,
        extend: Callable[[SessionState], None],
        reply: str,
    ) -> None:
        state.pending_followup = None
        if reply:
            console_ui.emit_reply(reply)
            self._speak_with_overlay(reply, state)
            remember_chat_turn(
                state, text, reply, max_turns=self._config.chat_memory_turns
            )
            extend(state)
        else:
            self._cant_help(extend, state)

    def _handle_unknown(
        self,
        text: str,
        state: SessionState,
        extend: Callable[[SessionState], None],
        chat_ctx: str | None,
        intent_type: str,
    ) -> None:
        state.pending_followup = None
        reply = None
        if self._allow_chat_fallback and intent_type == "unknown":
            if self._use_llm:
                console_ui.emit_thinking()
                self._set_overlay_phase("thinking")
            payload = text
            if chat_ctx:
                payload = f"{chat_ctx}\n\nLatest utterance: {text}"
            reply = self._parser.chat_reply(payload)
        if reply:
            console_ui.emit_reply(reply)
            self._speak_with_overlay(reply, state)
            remember_chat_turn(
                state, text, reply, max_turns=self._config.chat_memory_turns
            )
            extend(state)
            return
        self._cant_help(extend, state)

    def _handle_clarify(
        self,
        intent: dict[str, Any],
        state: SessionState,
        extend: Callable[[SessionState], None],
    ) -> None:
        reply = str(intent.get("reply", "")).strip()
        pending = str(intent.get("pending", "volume")).strip().lower()
        if pending not in VALID_CLARIFY_PENDING:
            pending = "volume"
        if reply:
            console_ui.emit_reply(reply)
            self._speak_with_overlay(reply, state)
            state.pending_followup = {"reply": reply, "pending": pending}
            remember_chat_turn(
                state, "", reply, max_turns=self._config.chat_memory_turns
            )
            extend(state)
        else:
            state.pending_followup = None
            console_ui.emit("I need a bit more detail for that.", style="yellow")
            self._speak_with_overlay("I need a bit more detail for that.", state)
            extend(state)

    def _cant_help(self, extend: Callable[[SessionState], None], state: SessionState) -> None:
        if self._use_llm and not self._llm_ready:
            spoken = (
                "My language model is still starting or failed to load. "
                "Wait a minute after startup, or run Install Dora again."
            )
            console_ui.emit(spoken, style="yellow")
            self._speak_with_overlay(spoken, state)
        else:
            console_ui.emit("I can't help with that command.", style="yellow")
            self._speak_with_overlay("I can't help with that command.", state)
        extend(state)

    @staticmethod
    def _print_result(message: str, style: str) -> None:
        console_ui.emit_result(message, style=style)

    def _extend_wake_after_response(self, state: SessionState) -> None:
        if self._listener is not None and self._wake_word_enabled:
            state.wake_armed_until = time.time() + self._post_response_listen_window_sec
