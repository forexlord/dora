from unittest.mock import MagicMock, patch

from core.win_wmi import get_brightness_percent_wmi, set_brightness_percent_wmi


class _FakeMonitor:
    def __init__(self, level: int) -> None:
        self.CurrentBrightness = level


class _FakeMethod:
    def WmiSetBrightness(self, _timeout: int, level: int) -> None:
        self.last_level = level


@patch("core.win_wmi._wmi_root")
def test_get_brightness_reads_first_monitor(mock_root: MagicMock) -> None:
    wmi = MagicMock()
    wmi.InstancesOf.return_value = [_FakeMonitor(42)]
    mock_root.return_value = wmi
    ok, value, err = get_brightness_percent_wmi()
    assert ok is True
    assert value == 42
    assert err == ""


@patch("core.win_wmi._wmi_root", return_value=None)
def test_get_brightness_unavailable_when_wmi_missing(_mock_root: MagicMock) -> None:
    ok, value, err = get_brightness_percent_wmi()
    assert ok is False
    assert value is None
    assert "not available" in err.lower()


@patch("core.win_wmi._wmi_root")
def test_set_brightness_calls_wmi_method(mock_root: MagicMock) -> None:
    method = _FakeMethod()
    wmi = MagicMock()
    wmi.InstancesOf.return_value = [method]
    mock_root.return_value = wmi
    ok, msg = set_brightness_percent_wmi(75)
    assert ok is True
    assert "75" in msg
    assert method.last_level == 75


@patch("core.win_wmi._wmi_root")
def test_set_brightness_clamps_percent(mock_root: MagicMock) -> None:
    method = _FakeMethod()
    wmi = MagicMock()
    wmi.InstancesOf.return_value = [method]
    mock_root.return_value = wmi
    ok, _msg = set_brightness_percent_wmi(500)
    assert ok is True
    assert method.last_level == 100
