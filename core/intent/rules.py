"""Fast path: keyword-based open / close / shutdown / confirm."""

from __future__ import annotations

import re
from typing import Any

from .constants import (
    CLOSE_WORDS,
    CONFIRM_WORDS,
    DEFAULT_VOLUME_STEP_PERCENT,
    FORCE_CLOSE_WORDS,
    OPEN_WORDS,
    SHUTDOWN_WORDS,
)


def extract_target_after_keyword(normalized: str, keywords: frozenset[str]) -> str | None:
    """
    Extract app/target after an open/close keyword anywhere in the phrase.
    Example: "can you please open file explorer" -> "file explorer"
    """
    match_end = -1
    for keyword in sorted(keywords, key=len, reverse=True):
        match = re.search(rf"\b{re.escape(keyword)}\b", normalized)
        if match:
            match_end = max(match_end, match.end())
    if match_end == -1:
        return None

    target = normalized[match_end:].strip(" ,.!?:;")
    if not target:
        return None

    filler_prefix = re.compile(
        r"^(please|the|my|a|an|app|application|for|me|to|just|now)\b\s*",
        re.IGNORECASE,
    )
    while True:
        cleaned = filler_prefix.sub("", target).strip()
        if cleaned == target:
            break
        target = cleaned

    return target or None


def extract_target_after_kill(normalized: str) -> str | None:
    """Match 'kill <app>' / 'kill the <app>' (word-boundary kill, not e.g. skill)."""
    m = re.search(r"\bkill\s+(?:the\s+)?(.+)$", normalized)
    if not m:
        return None
    target = m.group(1).strip(" ,.!?:;")
    if not target:
        return None
    filler_prefix = re.compile(
        r"^(please|the|my|a|an|app|application|for|me|to|just|now)\b\s*",
        re.IGNORECASE,
    )
    while True:
        cleaned = filler_prefix.sub("", target).strip()
        if cleaned == target:
            break
        target = cleaned
    return target or None


def parse_rule_intent(normalized: str) -> dict[str, Any] | None:
    open_target = extract_target_after_keyword(normalized, OPEN_WORDS)
    if open_target:
        return {"type": "open", "app": open_target}

    force_target = extract_target_after_keyword(normalized, FORCE_CLOSE_WORDS)
    if force_target:
        return {"type": "close", "app": force_target, "force": True}

    kill_target = extract_target_after_kill(normalized)
    if kill_target:
        return {"type": "close", "app": kill_target, "force": True}

    close_target = extract_target_after_keyword(normalized, CLOSE_WORDS)
    if close_target:
        return {"type": "close", "app": close_target, "force": False}

    for word in SHUTDOWN_WORDS:
        if normalized == word or normalized.startswith(word + " ") or f" {word} " in normalized:
            return {"type": "shutdown"}

    if normalized in CONFIRM_WORDS:
        return {"type": "confirm"}

    return None


_BATTERY_QUERY_RE = re.compile(
    r"\b("
    r"battery|batteries|battery level|battery percentage|battery percent|"
    r"charge level|how much charge|power left|remaining charge|"
    r"percent charge|charging status|am i charging|on battery|plugged in"
    r")\b",
    re.IGNORECASE,
)


def parse_battery_status_intent(normalized: str) -> dict[str, Any] | None:
    """Read real battery % from Windows — never guess with the LLM."""
    if not _BATTERY_QUERY_RE.search(normalized):
        return None
    if re.search(r"\b(open|close|launch|start|run)\b", normalized, re.IGNORECASE):
        return None
    return {"type": "battery_status"}


_VOLUME_CHANGE_RE = re.compile(
    r"\b("
    r"mute|unmute|louder|quieter|turn up|turn down|increase|decrease|"
    r"raise|lower|set|change|adjust|make it"
    r")\b",
    re.IGNORECASE,
)

_VOLUME_STATUS_RE = re.compile(
    r"\b("
    r"volume status|current volume|volume level|how loud|how quiet|"
    r"volume percentage|volume percent|what(?:'s| is) (?:the |my )?volume|"
    r"my volume|is (?:it |the volume )?muted|am i muted"
    r")\b",
    re.IGNORECASE,
)

_VOLUME_QUERY_HINT_RE = re.compile(
    r"\b(status|level|percentage|percent|how loud|how quiet|muted)\b",
    re.IGNORECASE,
)


def parse_volume_control_intent(normalized: str) -> dict[str, Any] | None:
    """Mute, unmute, louder, quieter — including STT forms like \"mutes my audio\"."""
    if parse_volume_status_intent(normalized):
        return None
    n = normalized
    if re.search(r"\bunmute\b", n, re.IGNORECASE):
        return {"type": "volume_unmute"}
    if re.search(r"\b(mute[ds]?|muting)\b", n, re.IGNORECASE):
        return {"type": "volume_mute"}
    step = int(DEFAULT_VOLUME_STEP_PERCENT)
    if re.search(
        r"\b(louder|turn up|increase(?:\s+the)?\s+volume|raise(?:\s+the)?\s+volume)\b",
        n,
        re.IGNORECASE,
    ):
        return {"type": "volume_relative", "delta_percent": step}
    if re.search(
        r"\b(quieter|turn down|decrease(?:\s+the)?\s+volume|lower(?:\s+the)?\s+volume)\b",
        n,
        re.IGNORECASE,
    ):
        return {"type": "volume_relative", "delta_percent": -step}
    return None


def parse_volume_status_intent(normalized: str) -> dict[str, Any] | None:
    """Read real volume % and mute from Windows — never guess with the LLM."""
    if _VOLUME_CHANGE_RE.search(normalized) and not _VOLUME_STATUS_RE.search(normalized):
        return None
    if _VOLUME_STATUS_RE.search(normalized):
        return {"type": "volume_status"}
    if re.search(r"\bvolume\b", normalized, re.IGNORECASE) and _VOLUME_QUERY_HINT_RE.search(
        normalized
    ):
        return {"type": "volume_status"}
    return None


_CREATOR_RE = re.compile(
    r"\b("
    r"who (?:made|created|built) you|who is your creator|who created you|"
    r"who made dora|your creator|who(?:'s| is) your (?:maker|developer|author)"
    r")\b",
    re.IGNORECASE,
)

_NAME_RE = re.compile(
    r"\b(what(?:'s| is) your name|who are you|what are you called)\b",
    re.IGNORECASE,
)


_CREATOR_MORE_RE = re.compile(
    r"\b("
    r"more about your creator|tell me more about (?:him|your creator|recovery)|"
    r"who is recovery eyo|about recovery eyo"
    r")\b",
    re.IGNORECASE,
)


def parse_identity_intent(normalized: str) -> dict[str, Any] | None:
    """Fixed facts about Dora — avoid LLM inventing Microsoft etc."""
    from .constants import DORA_CREATOR_MORE_REPLY, DORA_CREATOR_REPLY, DORA_NAME_REPLY

    if _CREATOR_MORE_RE.search(normalized):
        return {"type": "chat", "reply": DORA_CREATOR_MORE_REPLY}
    if _CREATOR_RE.search(normalized):
        return {"type": "chat", "reply": DORA_CREATOR_REPLY}
    if _NAME_RE.search(normalized):
        return {"type": "chat", "reply": DORA_NAME_REPLY}
    return None


_ACTION_VERB_RE = re.compile(
    r"\b("
    r"open|close|launch|start|run|load|kill|shutdown|shut\s*down|"
    r"mute[ds]?|muting|unmute|"
    r"volume|brightness|wifi|hotspot|louder|quieter|brighter|dimmer|dim|"
    r"increase|decrease|set|turn\s+on|turn\s+off|force\s+close|force\s+quit|"
    r"force\s+kill|hard\s+close"
    r")\b",
    re.IGNORECASE,
)

_SESSION_END_EXACT: frozenset[str] = frozenset(
    {
        "bye",
        "good bye",
        "goodbye",
        "thank you",
        "thanks",
        "thank you very much",
        "thanks a lot",
        "cheers",
    }
)

_SESSION_END_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^(thanks?|thank you|thx)\b",
        r"\b(goodbye|good bye|bye bye|see you|see ya|gotta go)\b",
        r"\b(that was helpful|that helped|that was great|that was good|very helpful)\b",
        r"\b(that'?s all|thats all|all set|i'?m done|im done|we'?re done|nothing else)\b",
        r"\b(no more questions|don'?t need anything else|i'?m good now)\b",
        r"\bappreciate (it|your help|the help)\b",
    )
)


def is_session_end_phrase(normalized: str) -> bool:
    """
    User is wrapping up (thanks, goodbye, done) — end the wake session.
    Matches natural speech, not only exact \"thank you\".
    """
    n = normalized.strip()
    if not n:
        return False
    if n in _SESSION_END_EXACT:
        return True
    return any(p.search(n) for p in _SESSION_END_PATTERNS)


_QUICK_DISMISS_PHRASES: tuple[str, ...] = (
    "never mind",
    "forget it",
    "no thanks",
    "nothing thanks",
    "cancel that",
    "stop listening",
    "that was wrong",
    "that's wrong",
    "that is wrong",
    "not that",
    "wrong app",
    "wrong one",
)


def parse_quick_chat_intent(normalized: str) -> dict[str, Any] | None:
    """
    Fast, local intents for short corrections / dismissals so we skip Ollama.

    Only matches when there is no obvious action verb (open/close/volume/…),
    so phrasing like \"no open chrome\" still falls through to rules or the LLM.
    """
    n = normalized.strip()
    if not n or _ACTION_VERB_RE.search(n):
        return None

    for phrase in _QUICK_DISMISS_PHRASES:
        if re.search(rf"\b{re.escape(phrase)}\b", n):
            return {"type": "chat", "reply": "Okay — what should I do next?"}

    if re.match(r"^no[.!?\s]*$", n, re.IGNORECASE):
        return {"type": "chat", "reply": "Got it. What would you like instead?"}

    return None
