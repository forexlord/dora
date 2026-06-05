"""Voice session state and short-turn chat memory."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SessionState:
    wake_armed_until: float = 0.0
    pending_followup: dict[str, str] | None = None
    chat_context: dict[str, str] | None = None


SESSION_END_TTS = "Call again when you need me."

CONFIRM_HEARD = frozenset(
    {"yes", "y", "yeah", "yep", "confirm", "confirmed", "oui", "si"}
)


def remember_chat_turn(
    state: SessionState, user_text: str, assistant_text: str
) -> None:
    reply = (assistant_text or "").strip()
    if not reply:
        return
    state.chat_context = {
        "user": " ".join(user_text.strip().split()),
        "assistant": reply,
    }


def build_chat_followup_context(state: SessionState, current_text: str) -> str | None:
    ctx = state.chat_context
    if not ctx or not str(ctx.get("assistant", "")).strip():
        return None
    return (
        "Context: Continue the same voice conversation.\n"
        f"Your last reply was: {ctx['assistant']}\n"
        f"Earlier they said: {ctx.get('user', '')}\n"
        f"They now say: {' '.join(current_text.strip().split())}\n"
        "Reply naturally as a follow-up. Do not repeat User: or Dora: labels."
    )


def clear_chat_context(state: SessionState) -> None:
    state.chat_context = None


def heard_is_confirmation(heard: str) -> bool:
    normalized = " ".join(heard.lower().strip().split())
    if not normalized:
        return False
    if normalized in CONFIRM_HEARD:
        return True
    first = normalized.split()[0]
    return first in CONFIRM_HEARD
