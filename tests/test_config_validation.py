import pytest

from core.config import ConfigValidationError, DoraConfig


def test_rejects_invalid_stt_engine() -> None:
    with pytest.raises(ConfigValidationError):
        DoraConfig.from_mapping({"stt_engine": "dragon"})


def test_rejects_invalid_chat_memory_turns() -> None:
    with pytest.raises(ConfigValidationError):
        DoraConfig.from_mapping({"chat_memory_turns": 0})


def test_warns_unknown_keys(caplog) -> None:
    import logging

    caplog.set_level(logging.WARNING)
    cfg = DoraConfig.from_mapping({"not_a_real_key": 1, "wake_word": "dora"})
    assert cfg.wake_word == "dora"
    assert "Unknown config keys" in caplog.text
