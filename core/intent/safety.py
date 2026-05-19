"""Content policy: profanity and unsafe model output."""

from __future__ import annotations

import re

from .constants import REFUSAL_REPLY

PROFANITY_RE = re.compile(
    r"\b("
    r"fuck|fucking|shit|bullshit|bitch|cunt|asshole|dick|cock|piss|pissing|"
    r"whore|slut|faggot|nigga|nigger|retard|bastard|motherfucker"
    r")\b",
    re.IGNORECASE,
)


def contains_profanity(text: str) -> bool:
    return bool(PROFANITY_RE.search(text))


def refusal_chat_intent() -> dict[str, str]:
    return {"type": "chat", "reply": REFUSAL_REPLY}


def sanitize_reply_text(reply: str) -> str:
    low = reply.lower()
    if contains_profanity(low):
        return REFUSAL_REPLY
    if "as an ai" in low or "as a language model" in low:
        return REFUSAL_REPLY
    return reply
