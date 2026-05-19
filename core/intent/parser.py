"""Orchestrates rule parsing, arithmetic, safety checks, and LLM intent resolution."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .arithmetic import try_spoken_arithmetic
from .constants import REFUSAL_REPLY, SHELL_LIKE_WORDS
from .conversational import should_use_model_chat
from .ollama_client import OllamaIntentBackend
from .rules import (
    parse_battery_status_intent,
    parse_identity_intent,
    parse_quick_chat_intent,
    parse_rule_intent,
    parse_volume_control_intent,
    parse_volume_status_intent,
)
from .safety import contains_profanity


class IntentParser:
    def __init__(
        self,
        ollama_model: str = "phi",
        use_ollama_fallback: bool = True,
        ollama_num_predict_resolve: int = 120,
        ollama_num_predict_chat: int = 128,
        ollama_temperature_resolve: float = 0.0,
        ollama_num_ctx: int | None = None,
        *,
        ollama_chat_model: str | None = None,
        fast_chat_path: bool = True,
        allow_chat: bool = True,
    ) -> None:
        self.use_ollama_fallback = use_ollama_fallback
        self._allow_chat = allow_chat
        self._fast_chat_path = fast_chat_path
        self._llm = OllamaIntentBackend(
            model=ollama_model,
            chat_model=ollama_chat_model,
            num_predict_resolve=ollama_num_predict_resolve,
            num_predict_chat=ollama_num_predict_chat,
            temperature_resolve=ollama_temperature_resolve,
            num_ctx=ollama_num_ctx,
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
        use_model_chat = should_use_model_chat(normalized) or bool(chat_followup_context)

        if (
            self._fast_chat_path
            and self._allow_chat
            and self.use_ollama_fallback
            and follow_up_context is None
            and use_model_chat
        ):
            if on_before_llm is not None:
                on_before_llm()
            payload = normalized
            if llm_context:
                payload = f"{llm_context}\n\nUser said: {normalized}"
            reply = self._llm.chat_reply(payload)
            if reply:
                return {"type": "chat", "reply": reply}

        if self.use_ollama_fallback and normalized not in SHELL_LIKE_WORDS:
            if on_before_llm is not None:
                on_before_llm()
            user_payload = normalized
            if llm_context:
                user_payload = f"{llm_context}\n\nUser said: {normalized}"
            ai = self._llm.resolve(user_payload)
            if ai:
                return ai

        return {"type": "unknown", "raw": text}

    def warmup_model(self) -> bool:
        return self._llm.warmup()

    def chat_reply(self, text: str) -> str | None:
        return self._llm.chat_reply(text)
