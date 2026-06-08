from unittest.mock import MagicMock, patch

import pytest

from core.listener.audio import (
    VoiceSetupError,
    input_device_ready,
    parse_audio_stream_retries,
    parse_input_device,
    pcm16le_rms,
    portaudio_errors,
    reset_audio_backend,
)


def test_portaudio_errors_includes_oserror() -> None:
    errs = portaudio_errors()
    assert OSError in errs


def test_parse_input_device_default_values() -> None:
    assert parse_input_device({}) is None
    assert parse_input_device({"audio_input_device": "default"}) is None
    assert parse_input_device({"audio_input_device": "auto"}) is None


def test_parse_input_device_index() -> None:
    assert parse_input_device({"audio_input_device": 2}) == 2


def test_parse_input_device_invalid() -> None:
    assert parse_input_device({"audio_input_device": "not-a-number"}) is None


def test_parse_audio_stream_retries_bounds() -> None:
    assert parse_audio_stream_retries({}) == 4
    assert parse_audio_stream_retries({"audio_stream_retries": 99}) == 12
    assert parse_audio_stream_retries({"audio_stream_retries": 0}) == 1
    assert parse_audio_stream_retries({"audio_stream_retries": "bad"}) == 4


def test_pcm16le_rms_silence_and_signal() -> None:
    assert pcm16le_rms(b"") == 0.0
    assert pcm16le_rms(b"\x00\x00" * 4) == 0.0
    loud = (20000).to_bytes(2, "little", signed=True)
    rms = pcm16le_rms(loud * 8)
    assert rms > 10000.0


@patch("core.listener.audio.sd.query_devices")
def test_input_device_ready_true(mock_query: MagicMock) -> None:
    mock_query.return_value = {"max_input_channels": 2}
    assert input_device_ready(None) is True
    mock_query.assert_called_with(kind="input")


@patch("core.listener.audio.sd.query_devices", side_effect=RuntimeError("no device"))
def test_input_device_ready_false_on_error(_mock_query: MagicMock) -> None:
    assert input_device_ready(0) is False


def test_reset_audio_backend_does_not_raise() -> None:
    reset_audio_backend()


def test_voice_setup_error_is_exception() -> None:
    with pytest.raises(VoiceSetupError):
        raise VoiceSetupError("missing model")
