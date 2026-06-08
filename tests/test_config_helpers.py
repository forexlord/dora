from core.config import DoraConfig
from core.config_helpers import (
    config_bool,
    config_float,
    config_get,
    config_int,
    config_optional_positive_int,
)


def test_config_get_from_dora_config() -> None:
    cfg = DoraConfig(wake_word="hey dora")
    assert config_get(cfg, "wake_word") == "hey dora"
    assert config_get(cfg, "missing", default=7) == 7


def test_config_bool_and_int_fallbacks() -> None:
    data = {"flag": "yes", "count": "nope"}
    assert config_bool(data, "flag") is True
    assert config_bool(data, "absent", default=True) is True
    assert config_int(data, "count", default=3) == 3


def test_config_float_and_optional_positive_int() -> None:
    data = {"rate": "1.5", "bad": "", "zero": 0, "threads": "8"}
    assert config_float(data, "rate") == 1.5
    assert config_float(data, "missing", default=2.0) == 2.0
    assert config_optional_positive_int(data, "bad") is None
    assert config_optional_positive_int(data, "zero") is None
    assert config_optional_positive_int(data, "threads") == 8
    assert config_float(data, "count", default=1.0) == 1.0
    assert config_optional_positive_int({"broken": "x"}) is None
