from core.config import DoraConfig
from core.wake_config import (
    build_wake_prefix_aliases,
    normalize_wake_hearing,
    parse_wake_phrases,
)


def test_parse_wake_phrases_from_wake_word() -> None:
    phrases, hint = parse_wake_phrases(DoraConfig(wake_word="dora"))
    assert "dora" in phrases
    assert "hey dora" in phrases
    assert "Say" in hint


def test_normalize_wake_hearing_alias() -> None:
    phrases, _ = parse_wake_phrases(DoraConfig(wake_word="dora"))
    prefixes = build_wake_prefix_aliases(phrases, DoraConfig())
    assert normalize_wake_hearing("a dora open chrome", phrases, prefixes) == "dora open chrome"


def test_normalize_wake_hearing_oh_alias_to_single_wake() -> None:
    phrases, _ = parse_wake_phrases(DoraConfig(wake_word="dora"))
    prefixes = build_wake_prefix_aliases(phrases, DoraConfig())
    assert (
        normalize_wake_hearing("oh dora what is my volume", phrases, prefixes)
        == "dora what is my volume"
    )
