from core.system_actions import apply_system_intent
from core.system_intents import SYSTEM_INTENT_TYPES, is_system_intent


def test_is_system_intent() -> None:
    assert is_system_intent("volume_mute")
    assert not is_system_intent("open")


def test_apply_system_intent_unknown() -> None:
    ok, msg = apply_system_intent({"type": "nope"})
    assert ok is False
    assert "Unknown" in msg


def test_system_intent_types_complete() -> None:
    assert "battery_status" in SYSTEM_INTENT_TYPES
    assert "wifi" in SYSTEM_INTENT_TYPES
