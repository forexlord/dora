from core.intent.safety import (
    contains_profanity,
    refusal_chat_intent,
    sanitize_reply_text,
    strip_dialogue_markup,
)


def test_strip_dialogue_markup() -> None:
    assert strip_dialogue_markup("User: open chrome") == "open chrome"


def test_profanity_detected() -> None:
    assert contains_profanity("what the fuck")


def test_refusal_intent_shape() -> None:
    intent = refusal_chat_intent()
    assert intent["type"] == "chat"
    assert "can't help" in intent["reply"].lower()


def test_sanitize_strips_roleplay() -> None:
    reply = sanitize_reply_text("Dora: Hello there.")
    assert "Hello" in reply
