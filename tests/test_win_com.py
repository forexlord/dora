from unittest.mock import MagicMock, patch

from core.win_com import SapiSpeechSynthesizer, SYSTEM_POWER_STATUS, get_battery_status_native


@patch("core.win_com.kernel32")
def test_battery_status_plugged_in(mock_kernel32: MagicMock) -> None:
    def fill_status(arg):
        obj = arg._obj
        obj.ACLineStatus = 1
        obj.BatteryFlag = 1
        obj.BatteryLifePercent = 80
        return 1

    mock_kernel32.GetSystemPowerStatus.side_effect = fill_status
    ok, msg = get_battery_status_native()
    assert ok is True
    assert "80 percent" in msg
    assert "charging" in msg


@patch("core.win_com.kernel32")
def test_battery_status_api_failure(mock_kernel32: MagicMock) -> None:
    mock_kernel32.GetSystemPowerStatus.return_value = 0
    ok, msg = get_battery_status_native()
    assert ok is False
    assert "Could not read battery" in msg


@patch("core.win_com.kernel32", None)
def test_battery_status_non_windows() -> None:
    ok, msg = get_battery_status_native()
    assert ok is False
    assert "Windows" in msg


def test_system_power_status_structure_size() -> None:
    assert SYSTEM_POWER_STATUS().BatteryLifePercent == 0


@patch("comtypes.client.CreateObject")
def test_sapi_speak_invokes_voice(mock_create: MagicMock) -> None:
    voice = MagicMock()
    mock_create.return_value = voice
    synth = SapiSpeechSynthesizer(rate=1, volume=50, preferred_voice="")
    synth.speak("hello")
    voice.Speak.assert_called_once_with("hello")


@patch("comtypes.client.CreateObject")
def test_sapi_skips_empty_text(mock_create: MagicMock) -> None:
    synth = SapiSpeechSynthesizer()
    synth.speak("   ")
    mock_create.assert_not_called()
