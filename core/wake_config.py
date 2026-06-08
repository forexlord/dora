"""Wake phrase configuration and STT alias normalization."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.config import DoraConfig

DEFAULT_WAKE_PREFIX_ALIASES: frozenset[str] = frozenset(
    {
        "hey",
        "hi",
        "ah",
        "a",
        "oh",
        "uh",
        "um",
        "yo",
        "so",
        "well",
        "the",
        "ho",
        "huh",
        "haw",
        "hay",
        "ok",
        "okay",
        "please",
        "can",
        "could",
        "would",
        "will",
        "may",
    }
)

WAKE_LEADING_FILLERS: frozenset[str] = frozenset(
    {
        "um",
        "uh",
        "oh",
        "a",
        "ah",
        "hey",
        "hi",
        "so",
        "well",
        "ok",
        "okay",
        "please",
        "yo",
    }
)

WAKE_POLITE_FILLERS: frozenset[str] = frozenset(
    {
        "can",
        "could",
        "would",
        "will",
        "may",
        "i",
        "you",
        "we",
        "me",
        "my",
        "the",
        "a",
        "an",
        "to",
        "for",
        "please",
        "just",
        "now",
        "um",
        "uh",
        "oh",
        "hey",
        "hi",
        "so",
        "well",
        "ok",
        "okay",
    }
)

# Whisper often mishears the wake name — map back before phrase matching.
DORA_WAKE_HOMOPHONES: dict[str, str] = {
    "doora": "dora",
    "adora": "dora",
    "deora": "dora",
    "dura": "dora",
    "doera": "dora",
    "dorah": "dora",
    "dorra": "dora",
}


@dataclass(frozen=True)
class WakeMatch:
    phrase: str
    command_tail: str


def _config_data(config: DoraConfig | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(config, DoraConfig):
        return config.to_dict()
    return config


def parse_wake_phrases(config: DoraConfig | Mapping[str, Any]) -> tuple[list[str], str]:
    """
    Build wake phrases (longest first for prefix matching) and overlay/TTS hint text.
    If wake_phrases is set in config, use it; else wake_word plus dora/hey-dora pairing.
    """
    data = _config_data(config)
    raw = data.get("wake_phrases")
    phrases: list[str] = []
    if isinstance(raw, list) and raw:
        phrases = [" ".join(str(x).lower().split()) for x in raw if str(x).strip()]
    else:
        wake = str(data.get("wake_word", "dora")).strip().lower() or "dora"
        phrases = [wake]
        if wake in {"dora", "hey dora"} or wake.endswith(" dora"):
            if "dora" not in phrases:
                phrases.append("dora")
            if "hey dora" not in phrases:
                phrases.append("hey dora")
    phrases = [p for p in phrases if p.strip()]
    if not phrases:
        phrases = ["dora", "hey dora"]
    phrases = sorted(set(phrases), key=len, reverse=True)

    hint = str(data.get("wake_hint", "")).strip()
    if not hint and phrases:
        short_first = sorted(phrases, key=len)
        parts = [f"“{p}”" for p in short_first]
        hint = "Say " + " or ".join(parts) + " when you need me."
    elif not hint:
        hint = "Say the wake phrase when you need me."
    return phrases, hint


def build_wake_prefix_aliases(
    wake_phrases: list[str], config: DoraConfig | Mapping[str, Any]
) -> frozenset[str]:
    prefixes = set(DEFAULT_WAKE_PREFIX_ALIASES)
    for phrase in wake_phrases:
        tokens = phrase.split()
        if tokens:
            prefixes.add(tokens[0])
    extra = _config_data(config).get("wake_prefix_aliases")
    if isinstance(extra, list):
        prefixes |= {str(x).lower().strip() for x in extra if str(x).strip()}
    return frozenset(prefixes)


def strip_spoken_punctuation(text: str) -> str:
    return " ".join(w.rstrip(".,!?;:") for w in text.split())


def wake_name_tokens(wake_phrases: list[str]) -> frozenset[str]:
    names: set[str] = set()
    for phrase in wake_phrases:
        for token in phrase.split():
            names.add(token.rstrip(".,!?;:"))
    return frozenset(names)


def apply_wake_homophones(text: str, wake_phrases: list[str]) -> str:
    names = wake_name_tokens(wake_phrases)
    if "dora" not in names:
        return text
    words = text.split()
    mapped = [DORA_WAKE_HOMOPHONES.get(w.rstrip(".,!?;:"), w.rstrip(".,!?;:")) for w in words]
    return " ".join(mapped)


def collapse_repeated_wake(text: str, wake_phrases: list[str]) -> str:
    """Dora Dora / hey dora hey dora → single wake phrase."""
    words = [w.rstrip(".,!?;:") for w in text.split()]
    if not words:
        return text
    for phrase in sorted(wake_phrases, key=len, reverse=True):
        phrase_words = phrase.split()
        n = len(phrase_words)
        if n == 0:
            continue
        i = 0
        collapsed: list[str] = []
        while i < len(words):
            if i + n <= len(words) and words[i : i + n] == phrase_words:
                if collapsed[-n:] != phrase_words:
                    collapsed.extend(phrase_words)
                i += n
                while i + n <= len(words) and words[i : i + n] == phrase_words:
                    i += n
            else:
                collapsed.append(words[i])
                i += 1
        words = collapsed
    return " ".join(words)


def is_filler_only(text: str) -> bool:
    tokens = [t.rstrip(".,!?;:") for t in text.split()]
    return bool(tokens) and all(t in WAKE_POLITE_FILLERS for t in tokens)


def rewrite_alias_to_two_word_phrase(
    normalized: str,
    w0: str,
    name: str,
    canonical: str,
    prefix_alts: frozenset[str],
) -> str:
    """STT: a dora / oh dora → canonical two-word phrase (e.g. hey dora)."""
    if normalized == canonical or normalized.startswith(canonical + " "):
        return normalized
    tokens = normalized.split()
    if len(tokens) < 2:
        return normalized
    t0 = tokens[0].rstrip(".,!?")
    t1 = tokens[1].rstrip(".,!?")
    if t1 != name.rstrip(".,!?"):
        return normalized
    if t0 not in prefix_alts and t0 != w0:
        return normalized
    rest = tokens[2:]
    return f"{canonical} {' '.join(rest)}".rstrip() if rest else canonical


def rewrite_alias_to_single_name(
    normalized: str, name: str, prefix_alts: frozenset[str]
) -> str:
    """STT: a dora → dora when single-word wake is configured."""
    if normalized == name or normalized.startswith(name + " "):
        return normalized
    tokens = normalized.split()
    if len(tokens) < 2:
        return normalized
    t0 = tokens[0].rstrip(".,!?")
    t1 = tokens[1].rstrip(".,!?")
    if t1 != name.rstrip(".,!?"):
        return normalized
    if t0 not in prefix_alts:
        return normalized
    rest = tokens[2:]
    return f"{name} {' '.join(rest)}".rstrip() if rest else name


def normalize_wake_hearing(
    normalized: str,
    wake_phrases: list[str],
    prefix_alts: frozenset[str],
) -> str:
    text = normalized
    for phrase in wake_phrases:
        parts = phrase.split()
        if len(parts) == 2:
            text = rewrite_alias_to_two_word_phrase(
                text, parts[0], parts[1], phrase, prefix_alts
            )
    for phrase in wake_phrases:
        if " " not in phrase:
            text = rewrite_alias_to_single_name(text, phrase, prefix_alts)
    return text


def preprocess_wake_hearing(
    normalized: str,
    wake_phrases: list[str],
    prefix_alts: frozenset[str],
) -> str:
    text = strip_spoken_punctuation(normalized)
    text = apply_wake_homophones(text, wake_phrases)
    text = collapse_repeated_wake(text, wake_phrases)
    return normalize_wake_hearing(text, wake_phrases, prefix_alts)


def match_wake_utterance(
    normalized: str,
    wake_phrases: list[str],
    prefix_alts: frozenset[str],
) -> WakeMatch | None:
    """
    Detect wake phrase in Whisper/Vosk output.
    Handles punctuation, repeated wake, homophones, and polite lead-in filler.
    """
    text = preprocess_wake_hearing(normalized, wake_phrases, prefix_alts)
    if not text:
        return None

    for phrase in wake_phrases:
        if text == phrase:
            return WakeMatch(phrase, "")
        if text.startswith(phrase + " "):
            return WakeMatch(phrase, text[len(phrase) :].strip())

    for filler in WAKE_LEADING_FILLERS:
        for phrase in wake_phrases:
            combo = f"{filler} {phrase}"
            if text == combo:
                return WakeMatch(phrase, "")
            if text.startswith(combo + " "):
                return WakeMatch(phrase, text[len(combo) :].strip())

    for phrase in wake_phrases:
        needle = f" {phrase}"
        idx = text.find(needle)
        if idx >= 0:
            before = text[:idx].strip()
            after = text[idx + len(needle) :].strip()
            if before and not is_filler_only(before):
                continue
            return WakeMatch(phrase, after)

    return None
