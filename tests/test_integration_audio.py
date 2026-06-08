"""Integration-style tests for the mic path with mocked PortAudio."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from core.listener.vosk_listener import VoiceListener


def _fake_vosk_model(tmp_path: Path) -> Path:
    for sub in ("am", "conf", "graph"):
        (tmp_path / sub).mkdir()
    return tmp_path


@patch("core.listener.vosk_listener.Model")
def test_vosk_listener_init_with_mock_model(mock_model: MagicMock, tmp_path: Path) -> None:
    mock_model.return_value = MagicMock()
    model_dir = _fake_vosk_model(tmp_path)
    listener = VoiceListener(model_path=str(model_dir), sample_rate=16000, input_device=1)
    assert listener.sample_rate == 16000
    assert listener.engine_label.startswith("Vosk")


@patch("core.listener.vosk_listener.input_device_ready", return_value=True)
@patch("core.listener.vosk_listener.sd.RawInputStream")
@patch("core.listener.vosk_listener.KaldiRecognizer")
@patch("core.listener.vosk_listener.Model")
def test_vosk_listen_once_idle_timeout(
    mock_model: MagicMock,
    mock_rec_cls: MagicMock,
    mock_stream_cls: MagicMock,
    _mock_ready: MagicMock,
    tmp_path: Path,
) -> None:
    mock_model.return_value = MagicMock()
    rec = MagicMock()
    rec.FinalResult.return_value = '{"text": ""}'
    rec.PartialResult.return_value = '{"partial": ""}'
    mock_rec_cls.return_value = rec
    mock_stream_cls.return_value.__enter__.return_value = MagicMock()
    mock_stream_cls.return_value.__exit__.return_value = False

    listener = VoiceListener(model_path=str(_fake_vosk_model(tmp_path)))
    text = listener.listen_once(
        idle_timeout_sec=0.01,
        idle_grace_sec=0.0,
        echo_status=False,
    )
    assert text == ""
    mock_stream_cls.assert_called_once()
