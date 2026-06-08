from unittest.mock import MagicMock, patch

from core.system_actions import (
    adjust_volume_percent,
    apply_system_intent,
    get_mute_state,
    get_volume_percent,
    get_volume_status,
    set_mute,
    set_volume_percent,
)


def _mock_volume(*, scalar: float = 0.5, muted: bool = False) -> MagicMock:
    vol = MagicMock()
    vol.GetMasterVolumeLevelScalar.return_value = scalar
    vol.GetMute.return_value = muted
    return vol


@patch("core.system_actions._endpoint_volume")
def test_get_volume_percent(mock_endpoint: MagicMock) -> None:
    mock_endpoint.return_value = (_mock_volume(scalar=0.42), "")
    ok, pct, err = get_volume_percent()
    assert ok is True
    assert pct == 42.0
    assert err == ""


@patch("core.system_actions._endpoint_volume")
def test_get_mute_state(mock_endpoint: MagicMock) -> None:
    mock_endpoint.return_value = (_mock_volume(muted=True), "")
    ok, muted, err = get_mute_state()
    assert ok is True
    assert muted is True
    assert err == ""


@patch("core.system_actions._endpoint_volume")
def test_set_volume_percent(mock_endpoint: MagicMock) -> None:
    vol = _mock_volume()
    mock_endpoint.return_value = (vol, "")
    ok, msg = set_volume_percent(80)
    assert ok is True
    vol.SetMasterVolumeLevelScalar.assert_called_once()
    assert "80" in msg


@patch("core.system_actions._endpoint_volume")
def test_set_mute(mock_endpoint: MagicMock) -> None:
    vol = _mock_volume()
    mock_endpoint.return_value = (vol, "")
    ok, msg = set_mute(True)
    assert ok is True
    assert msg == "Muted."


@patch("core.system_actions.get_volume_percent", return_value=(True, 40.0, ""))
@patch("core.system_actions.set_volume_percent", return_value=(True, "Volume set to about 60 percent."))
def test_adjust_volume_percent(mock_set: MagicMock, _mock_get: MagicMock) -> None:
    ok, msg = adjust_volume_percent(20.0)
    assert ok is True
    mock_set.assert_called_once_with(60.0)
    assert "40" in msg


@patch("core.system_actions.get_volume_percent", return_value=(True, 50.0, ""))
@patch("core.system_actions.get_mute_state", return_value=(True, False, ""))
def test_get_volume_status_unmuted(_mock_mute: MagicMock, _mock_vol: MagicMock) -> None:
    ok, msg = get_volume_status()
    assert ok is True
    assert "50 percent" in msg
    assert "not muted" in msg.lower()


@patch("core.system_actions.get_volume_percent", return_value=(True, 30.0, ""))
@patch("core.system_actions.get_mute_state", return_value=(True, True, ""))
def test_get_volume_status_muted(_mock_mute: MagicMock, _mock_vol: MagicMock) -> None:
    ok, msg = get_volume_status()
    assert ok is True
    assert "muted" in msg.lower()


@patch("core.system_actions._endpoint_volume", return_value=(None, "no device"))
def test_get_volume_percent_no_device(_mock_endpoint: MagicMock) -> None:
    ok, pct, err = get_volume_percent()
    assert ok is False
    assert pct is None
    assert "no device" in err


def test_apply_system_intent_volume_paths() -> None:
    with patch("core.system_actions.set_mute", return_value=(True, "Muted.")) as mock_mute:
        ok, msg = apply_system_intent({"type": "volume_mute"})
        assert ok is True
        mock_mute.assert_called_once_with(True)

    with patch("core.system_actions.adjust_volume_percent", return_value=(True, "louder")) as mock_adj:
        ok, msg = apply_system_intent({"type": "volume_relative", "delta_percent": 10})
        assert ok is True
        mock_adj.assert_called_once_with(10.0)
