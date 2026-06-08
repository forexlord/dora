from core.intent.rules import (
    parse_battery_status_intent,
    parse_rule_intent,
    parse_volume_control_intent,
    parse_volume_status_intent,
)


def test_parse_open_intent() -> None:
    intent = parse_rule_intent("please open google chrome")
    assert intent == {"type": "open", "app": "google chrome"}


def test_parse_open_strips_stt_junk_prefix() -> None:
    intent = parse_rule_intent("can you please open and was up")
    assert intent == {"type": "open", "app": "was up"}


def test_parse_force_close_intent() -> None:
    intent = parse_rule_intent("force close spotify")
    assert intent == {"type": "close", "app": "spotify", "force": True}


def test_parse_volume_mute() -> None:
    intent = parse_volume_control_intent("mute my audio")
    assert intent == {"type": "volume_mute"}


def test_parse_volume_status() -> None:
    intent = parse_volume_status_intent("what is my volume")
    assert intent == {"type": "volume_status"}


def test_parse_battery_status() -> None:
    intent = parse_battery_status_intent("what is my battery percentage")
    assert intent == {"type": "battery_status"}
