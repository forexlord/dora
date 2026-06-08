from core.config import DoraConfig
from core.wake_config import (
    build_wake_prefix_aliases,
    match_wake_utterance,
    normalize_wake_hearing,
    parse_wake_phrases,
    preprocess_wake_hearing,
)


def _phrases_and_prefixes() -> tuple[list[str], frozenset[str]]:
    phrases, _ = parse_wake_phrases(DoraConfig(wake_word="dora"))
    prefixes = build_wake_prefix_aliases(phrases, DoraConfig())
    return phrases, prefixes


def test_parse_wake_phrases_from_wake_word() -> None:
    phrases, hint = parse_wake_phrases(DoraConfig(wake_word="dora"))
    assert "dora" in phrases
    assert "hey dora" in phrases
    assert "Say" in hint


def test_normalize_wake_hearing_alias() -> None:
    phrases, prefixes = _phrases_and_prefixes()
    assert normalize_wake_hearing("a dora open chrome", phrases, prefixes) == "dora open chrome"


def test_normalize_wake_hearing_oh_alias_to_single_wake() -> None:
    phrases, prefixes = _phrases_and_prefixes()
    assert (
        preprocess_wake_hearing("oh dora what is my volume", phrases, prefixes)
        == "dora what is my volume"
    )


def test_match_wake_repeated_dora_with_punctuation() -> None:
    phrases, prefixes = _phrases_and_prefixes()
    match = match_wake_utterance("dora. dora.", phrases, prefixes)
    assert match is not None
    assert match.command_tail == ""


def test_match_wake_with_polite_leadin() -> None:
    phrases, prefixes = _phrases_and_prefixes()
    match = match_wake_utterance("can you please dora open brave", phrases, prefixes)
    assert match is not None
    assert match.command_tail == "open brave"


def test_match_wake_homophone_doora() -> None:
    phrases, prefixes = _phrases_and_prefixes()
    match = match_wake_utterance("hey doora open chrome", phrases, prefixes)
    assert match is not None
    assert match.command_tail == "open chrome"


def test_match_wake_with_command() -> None:
    phrases, prefixes = _phrases_and_prefixes()
    match = match_wake_utterance("dora open chrome", phrases, prefixes)
    assert match is not None
    assert match.command_tail == "open chrome"
