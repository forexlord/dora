"""Route utterances to the model vs the command resolver — no phrase lists."""

from __future__ import annotations

from .rules import _ACTION_VERB_RE


def should_use_model_chat(normalized: str) -> bool:
    """
    Use the model for a dynamic spoken reply unless this is clearly a PC command.

    No canned questions or answers: anything without an action verb (open, close,
    volume, mute, …) is handled by the model, including greetings, small talk,
    and open-ended questions.
    """
    n = normalized.strip()
    if not n:
        return False
    return _ACTION_VERB_RE.search(n) is None
