from core.intent.llm_client import coerce_json_number, parse_resolve_json


def test_parse_resolve_json_plain() -> None:
    assert parse_resolve_json('{"type":"open","app":"chrome"}') == {
        "type": "open",
        "app": "chrome",
    }


def test_parse_resolve_json_embedded() -> None:
    raw = 'Here you go {"type": "volume_mute"} thanks'
    assert parse_resolve_json(raw) == {"type": "volume_mute"}


def test_parse_resolve_json_invalid() -> None:
    assert parse_resolve_json("not json") is None
    assert parse_resolve_json("") is None


def test_coerce_json_number() -> None:
    assert coerce_json_number("20%") == 20.0
    assert coerce_json_number(None) is None
    assert coerce_json_number(True) is None
