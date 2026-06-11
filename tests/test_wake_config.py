from core.config import DoraConfig
from core.wake_config import (
    build_wake_prefix_aliases,
    match_wake_utterance,
    normalize_wake_hearing,
    parse_wake_phrases,
    preprocess_wake_hearing,
)


def _hey_dora_setup() -> tuple[list[str], frozenset[str]]:
    phrases, _ = parse_wake_phrases(DoraConfig())
    prefixes = build_wake_prefix_aliases(phrases, DoraConfig())
    return phrases, prefixes


def _legacy_dora_setup() -> tuple[list[str], frozenset[str]]:
    phrases, _ = parse_wake_phrases(DoraConfig(wake_word="dora", wake_phrases=[]))
    prefixes = build_wake_prefix_aliases(phrases, DoraConfig(wake_word="dora"))
    return phrases, prefixes


def test_parse_wake_phrases_default_hey_dora_only() -> None:
    phrases, hint = parse_wake_phrases(DoraConfig())
    assert phrases == ["hey dora"]
    assert "hey dora" in hint


def test_parse_wake_phrases_legacy_dora() -> None:
    phrases, _ = parse_wake_phrases(DoraConfig(wake_word="dora", wake_phrases=[]))
    assert "dora" in phrases
    assert "hey dora" in phrases


def test_normalize_wake_hearing_hi_dora() -> None:
    phrases, prefixes = _hey_dora_setup()
    assert (
        preprocess_wake_hearing("hi dora open chrome", phrases, prefixes)
        == "hey dora open chrome"
    )


def test_match_wake_repeated_hey_dora_with_punctuation() -> None:
    phrases, prefixes = _hey_dora_setup()
    match = match_wake_utterance("hey dora. hey dora.", phrases, prefixes)
    assert match is not None
    assert match.command_tail == ""


def test_match_wake_hey_dora_with_command() -> None:
    phrases, prefixes = _hey_dora_setup()
    match = match_wake_utterance("hey dora open chrome", phrases, prefixes)
    assert match is not None
    assert match.command_tail == "open chrome"


def test_bare_dora_does_not_wake_hey_dora_only() -> None:
    phrases, prefixes = _hey_dora_setup()
    assert match_wake_utterance("dora open chrome", phrases, prefixes) is None
    assert match_wake_utterance("dora. dora.", phrases, prefixes) is None


def test_can_dora_does_not_false_wake() -> None:
    phrases, prefixes = _hey_dora_setup()
    assert match_wake_utterance("can you please dora open brave", phrases, prefixes) is None


def test_match_wake_homophone_hey_doora() -> None:
    phrases, prefixes = _hey_dora_setup()
    match = match_wake_utterance("hey doora open chrome", phrases, prefixes)
    assert match is not None
    assert match.command_tail == "open chrome"


def test_legacy_dora_single_word_wake() -> None:
    phrases, prefixes = _legacy_dora_setup()
    match = match_wake_utterance("dora open chrome", phrases, prefixes)
    assert match is not None
    assert normalize_wake_hearing("a dora open chrome", phrases, prefixes) == "dora open chrome"
