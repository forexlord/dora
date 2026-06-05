"""Content policy: profanity and unsafe model output."""

from __future__ import annotations

import re

from .constants import REFUSAL_REPLY

_DIALOGUE_PREFIX_RE = re.compile(
    r"^\s*(?:user|dora|assistant|command|heard)\s*:\s*",
    re.IGNORECASE,
)
_ROLEPLAY_BLOCK_RE = re.compile(
    r"\n\s*(?:user|dora|assistant)\s*:",
    re.IGNORECASE,
)


def strip_dialogue_markup(text: str) -> str:
    """Remove pasted transcript labels (User:/Dora:) from mic or typed input."""
    cleaned = text.strip()
    while True:
        m = _DIALOGUE_PREFIX_RE.match(cleaned)
        if not m:
            break
        cleaned = cleaned[m.end() :].strip()
    return cleaned


_ASSISTANT_LINE_RE = re.compile(
    r"^\s*(?:dora|assistant)\s*:\s*(.+)$",
    re.IGNORECASE,
)


def strip_roleplay_from_reply(reply: str) -> str:
    """Drop model echoes of User:/Dora: script lines — never speak those aloud."""
    text = (reply or "").strip()
    if not text:
        return ""
    assistant_lines: list[str] = []
    plain_lines: list[str] = []
    for line in text.splitlines():
        m = _ASSISTANT_LINE_RE.match(line)
        if m:
            assistant_lines.append(m.group(1).strip())
            continue
        if _DIALOGUE_PREFIX_RE.match(line):
            continue
        line = line.strip()
        if line:
            plain_lines.append(line)
    if assistant_lines:
        return assistant_lines[-1]
    if plain_lines:
        return " ".join(plain_lines)
    text = _ROLEPLAY_BLOCK_RE.split(text, maxsplit=1)[0].strip()
    return _DIALOGUE_PREFIX_RE.sub("", text).strip() or text


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
    reply = strip_roleplay_from_reply(reply)
    if not reply:
        return REFUSAL_REPLY
    low = reply.lower()
    if contains_profanity(low):
        return REFUSAL_REPLY
    if "as an ai" in low or "as a language model" in low:
        return REFUSAL_REPLY
    return reply
