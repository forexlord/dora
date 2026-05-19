"""Deterministic spoken arithmetic (complements unreliable small LLMs)."""

from __future__ import annotations

import re


def _strip_trailing_noise(s: str) -> str:
    s = s.strip()
    for noise in (" please", " equals", " question", " mark"):
        if s.endswith(noise):
            s = s[: -len(noise)].strip()
    return s


def try_spoken_arithmetic(normalized: str) -> str | None:
    """
    Handle phrases like 'what is eighty five times fifty six' or '10 times 5'.
    Requires optional dependency: word2number (for word operands).
    """
    try:
        from word2number import w2n
    except ImportError:
        w2n = None

    def parse_pair(left: str, right: str) -> tuple[int, int] | None:
        left, right = left.strip(), _strip_trailing_noise(right)
        if not left or not right:
            return None
        try:
            if re.fullmatch(r"\d+", left) and re.fullmatch(r"\d+", right):
                return int(left), int(right)
            if w2n is None:
                return None
            return w2n.word_to_num(left), w2n.word_to_num(right)
        except (ValueError, AttributeError, KeyError):
            return None

    pairs: list[tuple[re.Pattern[str], str]] = [
        (
            re.compile(
                r"(?:what\s+is|what\'?s)\s+(.+?)\s+times\s+(.+)$",
                re.IGNORECASE,
            ),
            "times",
        ),
        (re.compile(r"^(.+?)\s+times\s+(.+)$", re.IGNORECASE), "times"),
        (
            re.compile(
                r"(?:what\s+is|what\'?s)\s+(.+?)\s+plus\s+(.+)$",
                re.IGNORECASE,
            ),
            "plus",
        ),
        (re.compile(r"^(.+?)\s+plus\s+(.+)$", re.IGNORECASE), "plus"),
        (
            re.compile(
                r"(?:what\s+is|what\'?s)\s+(.+?)\s+minus\s+(.+)$",
                re.IGNORECASE,
            ),
            "minus",
        ),
        (re.compile(r"^(.+?)\s+minus\s+(.+)$", re.IGNORECASE), "minus"),
    ]
    for pat, op in pairs:
        m = pat.match(normalized.strip())
        if not m:
            continue
        nums = parse_pair(m.group(1), m.group(2))
        if not nums:
            continue
        a, b = nums
        if op == "times":
            return f"{a} times {b} equals {a * b}."
        if op == "plus":
            return f"{a} plus {b} equals {a + b}."
        if op == "minus":
            return f"{a} minus {b} equals {a - b}."
    return None
