"""Fuzzy app-name resolution against a launch index."""

from __future__ import annotations

import difflib


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

    close = difflib.get_close_matches(app_key, list(candidates.keys()), n=1, cutoff=0.55)
    if close:
        close_ratio = difflib.SequenceMatcher(None, app_key, close[0]).ratio()
        if close_ratio > best_score:
            best_key = close[0]
            best_score = close_ratio

    if best_key is None:
        return None, 0.0
    return best_key, best_score
