from unittest.mock import patch

from core.system_actions import (
    apply_system_intent,
    get_brightness_percent,
    hotspot_set,
    hotspot_toggle,
    set_brightness_percent,
)


def test_hotspot_routes_to_settings_message() -> None:
    ok, msg = hotspot_toggle()
    assert ok is False
    assert "Settings" in msg
    ok2, msg2 = hotspot_set(True)
    assert ok2 is False
    assert "Settings" in msg2


def test_apply_system_hotspot_intent() -> None:
    ok, msg = apply_system_intent({"type": "hotspot"})
    assert ok is False
    assert "Mobile hotspot" in msg


@patch("core.win_wmi.get_brightness_percent_wmi", return_value=(True, 55, ""))
def test_get_brightness_delegates_to_wmi(mock_wmi) -> None:
    ok, value, err = get_brightness_percent()
    assert ok is True
    assert value == 55
    assert err == ""
    mock_wmi.assert_called_once()


@patch("core.win_wmi.set_brightness_percent_wmi", return_value=(True, "Brightness set to about 30 percent."))
def test_set_brightness_delegates_to_wmi(mock_wmi) -> None:
    ok, msg = set_brightness_percent(30)
    assert ok is True
    assert "30" in msg
    mock_wmi.assert_called_once_with(30)


@patch("core.system_actions.set_brightness_percent", return_value=(True, "Brightness set to about 60 percent."))
@patch("core.system_actions.get_brightness_percent", return_value=(True, 50, ""))
def test_apply_system_brightness_relative(_mock_get, mock_set) -> None:
    from core.system_actions import apply_system_intent

    ok, msg = apply_system_intent({"type": "brightness_relative", "delta_percent": 10})
    assert ok is True
    mock_set.assert_called_once_with(60)
    assert "60" in msg
