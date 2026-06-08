"""Orchestrates rule parsing, arithmetic, safety checks, and LLM intent resolution."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .arithmetic import try_spoken_arithmetic
from .constants import REFUSAL_REPLY, SHELL_LIKE_WORDS
from .conversational import should_use_model_chat
from .llm_client import GgufIntentBackend, last_llama_load_error
from .rules import (
    ACTION_VERB_RE,
    is_capabilities_question,
    parse_battery_status_intent,
    parse_identity_intent,
    parse_quick_chat_intent,
    parse_rule_intent,
    parse_volume_control_intent,
    parse_volume_status_intent,
)
from .safety import contains_profanity, strip_dialogue_markup


class IntentParser:
    def __init__(
        self,
        model_path: str,
        config: dict,
        use_llm_fallback: bool = True,
        num_predict_resolve: int = 120,
        num_predict_chat: int = 128,
        temperature_resolve: float = 0.0,
        n_ctx: int | None = None,
        n_threads: int = 0,
        *,
        fast_chat_path: bool = True,
        allow_chat: bool = True,
    ) -> None:
        self.use_llm_fallback = use_llm_fallback
        self._allow_chat = allow_chat
        self._fast_chat_path = fast_chat_path
        self._llm = GgufIntentBackend(
            model_path=model_path,
            config=config,
            num_predict_resolve=num_predict_resolve,
            num_predict_chat=num_predict_chat,
            temperature_resolve=temperature_resolve,
            n_ctx=n_ctx,
            n_threads=n_threads,
        )

    @staticmethod
    def _merge_llm_context(*parts: str | None) -> str | None:
        chunks = [p.strip() for p in parts if p and p.strip()]
        return "\n\n".join(chunks) if chunks else None

    def parse(
        self,
        text: str,
        on_before_llm: Callable[[], None] | None = None,
        follow_up_context: str | None = None,
        chat_followup_context: str | None = None,
    ) -> dict[str, Any]:
        text = strip_dialogue_markup(text)
        normalized = " ".join(text.lower().strip().split())
        if not normalized:
            return {"type": "unknown", "raw": text}

        if contains_profanity(normalized):
            return {"type": "chat", "reply": REFUSAL_REPLY}

        ar = try_spoken_arithmetic(normalized)
        if ar:
            return {"type": "chat", "reply": ar}

        rule_intent = parse_rule_intent(normalized)
        if rule_intent:
            return rule_intent

        identity = parse_identity_intent(normalized)
        if identity:
            return identity

        volume_control = parse_volume_control_intent(normalized)
        if volume_control:
            return volume_control

        volume_status = parse_volume_status_intent(normalized)
        if volume_status:
            return volume_status

        battery = parse_battery_status_intent(normalized)
        if battery:
            return battery

        quick = parse_quick_chat_intent(normalized)
        if quick:
            return quick

        llm_context = self._merge_llm_context(follow_up_context, chat_followup_context)
        caps_question = is_capabilities_question(normalized)
        use_model_chat = should_use_model_chat(normalized) or (
            bool(chat_followup_context) and not ACTION_VERB_RE.search(normalized)
        )

        if (
            self._fast_chat_path
            and self._allow_chat
            and self.use_llm_fallback
            and follow_up_context is None
            and use_model_chat
        ):
            if on_before_llm is not None:
                on_before_llm()
            payload = normalized
            extra: list[str] = []
            if llm_context:
                extra.append(llm_context)
            if caps_question:
                extra.append(
                    "The user is asking what you can help with on this Windows PC. "
                    "Answer using only the real abilities from your instructions. "
                    "Do not refuse this question."
                )
            if extra:
                payload = "\n\n".join(extra + [f"Latest utterance: {normalized}"])
            reply = self._llm.chat_reply(payload)
            if reply:
                return {"type": "chat", "reply": reply}

        if self.use_llm_fallback and normalized not in SHELL_LIKE_WORDS:
            if on_before_llm is not None:
                on_before_llm()
            user_payload = normalized
            resolve_extra: list[str] = []
            if llm_context:
                resolve_extra.append(llm_context)
            if caps_question:
                resolve_extra.append(
                    "The user is asking what you can help with on this Windows PC."
                )
            if resolve_extra:
                user_payload = "\n\n".join(resolve_extra + [f"Latest utterance: {normalized}"])
            ai = self._llm.resolve(user_payload)
            if ai:
                return ai

        return {"type": "unknown", "raw": text}

    def warmup_model(self) -> bool:
        return self._llm.warmup()

    def llm_load_error(self) -> str | None:
        return last_llama_load_error()

    def chat_reply(self, text: str) -> str | None:
        return self._llm.chat_reply(text)
