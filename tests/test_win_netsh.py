from unittest.mock import MagicMock, patch

from core.win_netsh import _find_wifi_interface, wifi_set_netsh, wifi_toggle_netsh


def _run_result(code: int, stdout: str = "", stderr: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = code
    result.stdout = stdout
    result.stderr = stderr
    return result


@patch("core.win_netsh.run_no_console")
def test_find_wifi_interface_parses_name(mock_run: MagicMock) -> None:
    mock_run.return_value = _run_result(
        0,
        "Enabled  Connected  Dedicated  Wi-Fi\n",
    )
    assert _find_wifi_interface() == "Wi-Fi"


@patch("core.win_netsh.run_no_console")
def test_wifi_set_enables_adapter(mock_run: MagicMock) -> None:
    mock_run.side_effect = [
        _run_result(0, "Enabled  Connected  Dedicated  Wi-Fi\n"),
        _run_result(0),
    ]
    ok, msg = wifi_set_netsh(True)
    assert ok is True
    assert "on" in msg.lower()


@patch("core.win_netsh.run_no_console")
def test_wifi_toggle_no_adapter(mock_run: MagicMock) -> None:
    mock_run.return_value = _run_result(0, "Admin State    State          Type    Interface\n")
    ok, msg = wifi_toggle_netsh()
    assert ok is False
    assert "No Wi-Fi" in msg
