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

CONFIRM_WORDS = frozenset(
    {
        "yes",
        "y",
        "yeah",
        "yep",
        "yup",
        "confirm",
        "confirmed",
        "sure",
        "ok",
        "okay",
        "oui",
        "si",
        "absolutely",
        "correct",
        "right",
        "allow",
        "proceed",
        "affirmative",
        "definitely",
        "fine",
        "alright",
        "aye",
    }
)

CONFIRM_PHRASES: tuple[str, ...] = (
    "go ahead",
    "go for it",
    "do it",
    "open it",
    "that's right",
    "that is right",
    "sounds good",
    "of course",
    "why not",
    "sure thing",
    "you bet",
    "please do",
    "do that",
    "that's fine",
    "that is fine",
    "works for me",
)

DENY_WORDS = frozenset(
    {"no", "nope", "nah", "cancel", "stop", "dont", "negative", "never"}
)

DENY_PHRASES: tuple[str, ...] = (
    "don't",
    "do not",
    "no thanks",
    "not now",
    "never mind",
    "nevermind",
    "forget it",
)

# Back-compat alias used by text-mode confirm input.
CONFIRM_HEARD = CONFIRM_WORDS


def _normalize_heard(heard: str) -> str:
    return " ".join(heard.lower().strip().split())


def _strip_word_punct(word: str) -> str:
    return word.strip(".,!?;:")


def heard_is_denial(heard: str) -> bool:
    normalized = _normalize_heard(heard)
    if not normalized:
        return False
    if normalized in DENY_WORDS:
        return True
    for phrase in DENY_PHRASES:
        if phrase in normalized:
            return True
    first = _strip_word_punct(normalized.split()[0]) if normalized.split() else ""
    return first in DENY_WORDS


def heard_is_likely_prompt_echo(heard: str, prompt: str) -> bool:
    """True when the mic likely captured TTS reading the confirmation prompt."""
    h = _normalize_heard(heard)
    p = _normalize_heard(prompt)
    if not h or not p:
        return False
    if len(h) <= 12 and heard_is_confirmation(h):
        return False
    if h in p or p in h:
        return True
    hw = set(h.split())
    pw = set(p.split())
    overlap = hw & pw
    if len(overlap) >= 3:
        return True
    return len(overlap) >= 2 and len(hw) >= 4


def heard_is_confirmation(heard: str) -> bool:
    normalized = _normalize_heard(heard)
    if not normalized:
        return False
    if heard_is_denial(normalized):
        return False
    if normalized in CONFIRM_WORDS:
        return True
    for phrase in CONFIRM_PHRASES:
        if phrase in normalized:
            return True
    for word in normalized.split():
        if _strip_word_punct(word) in CONFIRM_WORDS:
            return True
    return False


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
