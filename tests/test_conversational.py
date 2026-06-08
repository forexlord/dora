from core.intent.conversational import should_use_model_chat


def test_should_use_model_chat_for_greeting() -> None:
    assert should_use_model_chat("hello there") is True


def test_should_use_model_chat_false_for_command() -> None:
    assert should_use_model_chat("open chrome") is False


def test_should_use_model_chat_empty() -> None:
    assert should_use_model_chat("   ") is False
