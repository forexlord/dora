"""Voice session state and multi-turn chat memory."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChatTurn:
    user: str
    assistant: str


@dataclass
class SessionState:
    wake_armed_until: float = 0.0
    pending_followup: dict[str, str] | None = None
    chat_turns: list[ChatTurn] = field(default_factory=list)


SESSION_END_TTS = "Call again when you need me."

CONFIRM_HEARD = frozenset(
    {"yes", "y", "yeah", "yep", "confirm", "confirmed", "oui", "si"}
)


def remember_chat_turn(
    state: SessionState,
    user_text: str,
    assistant_text: str,
    *,
    max_turns: int = 4,
) -> None:
    reply = (assistant_text or "").strip()
    user = " ".join(user_text.strip().split())
    if not reply and not user:
        return
    state.chat_turns.append(ChatTurn(user=user, assistant=reply))
    limit = max(1, int(max_turns))
    if len(state.chat_turns) > limit:
        state.chat_turns = state.chat_turns[-limit:]


def build_chat_followup_context(
    state: SessionState,
    current_text: str,
    *,
    max_turns: int = 4,
) -> str | None:
    if not state.chat_turns:
        return None
    limit = max(1, int(max_turns))
    recent = state.chat_turns[-limit:]
    lines = ["Context: Continue the same voice conversation."]
    for turn in recent:
        if turn.user:
            lines.append(f"They said: {turn.user}")
        if turn.assistant:
            lines.append(f"Your last reply was: {turn.assistant}")
    lines.append(f"They now say: {' '.join(current_text.strip().split())}")
    lines.append("Reply naturally as a follow-up. Do not repeat User: or Dora: labels.")
    return "\n".join(lines)


def clear_chat_context(state: SessionState) -> None:
    state.chat_turns.clear()


def heard_is_confirmation(heard: str) -> bool:
    normalized = " ".join(heard.lower().strip().split())
    if not normalized:
        return False
    if normalized in CONFIRM_HEARD:
        return True
    first = normalized.split()[0]
    return first in CONFIRM_HEARD
