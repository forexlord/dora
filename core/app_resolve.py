"""Fuzzy app-name resolution against a launch index."""

from __future__ import annotations

import difflib
import os

# Spoken names that differ from Start Menu labels (applied when there is no exact index hit).
APP_ALIASES: dict[str, str] = {
    "file manager": "file explorer",
    "file browser": "file explorer",
    "files": "file explorer",
    "windows explorer": "file explorer",
    "my computer": "file explorer",
    "this pc": "file explorer",
    # Common STT mishearings for WhatsApp
    "was up": "whatsapp",
    "was app": "whatsapp",
    "whats app": "whatsapp",
    "what's app": "whatsapp",
    "whatsup": "whatsapp",
    "watsapp": "whatsapp",
    # Brave browser — common Whisper mishearings
    "breathe": "brave",
    "breath": "brave",
    "brief": "brave",
    "brave browser": "brave",
}

_SHARED_SUFFIXES = frozenset({"manager", "app", "application", "program", "tool"})


def apply_app_alias(app_key: str) -> str:
    """Map common spoken names to indexed Start Menu keys."""
    return APP_ALIASES.get(app_key.strip().lower(), app_key)


def _leading_token_conflict(query: str, candidate: str) -> bool:
    """
    Reject matches that only share a generic suffix, e.g. file manager vs task manager.
    """
    q_parts = query.split()
    c_parts = candidate.split()
    if len(q_parts) < 2 or len(c_parts) < 2:
        return False
    if q_parts[-1] != c_parts[-1] or q_parts[-1] not in _SHARED_SUFFIXES:
        return False
    return q_parts[0] != c_parts[0]


def resolve_app_key(app_key: str, candidates: dict[str, str]) -> tuple[str | None, float]:
    if app_key in candidates:
        return app_key, 1.0
    if not candidates:
        return None, 0.0

    def compact(text: str) -> str:
        return "".join(ch for ch in text.lower() if ch.isalnum())

    def consonant_key(text: str) -> str:
        source = compact(text)
        if not source:
            return ""
        vowels = set("aeiou")
        out: list[str] = []
        prev = ""
        for ch in source:
            if ch in vowels:
                continue
            if ch != prev:
                out.append(ch)
                prev = ch
        return "".join(out)

    query_tokens = set(app_key.split())
    query_compact = compact(app_key)
    query_cons = consonant_key(app_key)
    best_key = None
    best_score = 0.0
    for candidate in candidates:
        if _leading_token_conflict(app_key, candidate):
            continue
        cand_tokens = set(candidate.split())
        overlap = len(query_tokens & cand_tokens)
        token_score = overlap / max(len(query_tokens), len(cand_tokens), 1)
        ratio = difflib.SequenceMatcher(None, app_key, candidate).ratio()
        compact_ratio = difflib.SequenceMatcher(None, query_compact, compact(candidate)).ratio()
        cons_ratio = difflib.SequenceMatcher(None, query_cons, consonant_key(candidate)).ratio()
        score = (0.35 * ratio) + (0.15 * token_score) + (0.35 * compact_ratio) + (0.15 * cons_ratio)
        if score > best_score:
            best_key = candidate
            best_score = score

    close = difflib.get_close_matches(app_key, list(candidates.keys()), n=3, cutoff=0.55)
    for match in close:
        if _leading_token_conflict(app_key, match):
            continue
        close_ratio = difflib.SequenceMatcher(None, app_key, match).ratio()
        if close_ratio > best_score:
            best_key = match
            best_score = close_ratio

    if best_key is None or best_score < 0.58:
        return None, 0.0
    return best_key, best_score


def well_known_windows_apps() -> dict[str, str]:
    """Built-in shortcuts when Start Menu indexing misses common system apps."""
    windir = os.environ.get("WINDIR", r"C:\Windows")
    system32 = os.path.join(windir, "System32")
    entries: dict[str, str] = {}
    explorer = os.path.join(windir, "explorer.exe")
    taskmgr = os.path.join(system32, "Taskmgr.exe")
    if os.path.isfile(explorer):
        entries["file explorer"] = explorer
        entries["explorer"] = explorer
    if os.path.isfile(taskmgr):
        entries["task manager"] = taskmgr
    return entries
