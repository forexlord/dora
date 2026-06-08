from unittest.mock import MagicMock, patch

import numpy as np

from core.listener.whisper_listener import (
    WhisperVoiceListener,
    _default_whisper_compute_type,
    _normalize_whisper_model,
    _resolve_whisper_device,
)


def test_normalize_whisper_model_english_suffix() -> None:
    assert _normalize_whisper_model("small", "en") == "small.en"
    assert _normalize_whisper_model("base", "en") == "base.en"
    assert _normalize_whisper_model("small.en", "en") == "small.en"


def test_default_compute_type_cpu_int8() -> None:
    assert _default_whisper_compute_type("cpu", "default") == "int8"


def test_resolve_whisper_device_cpu() -> None:
    assert _resolve_whisper_device("cpu") == "cpu"


@patch("faster_whisper.WhisperModel")
def test_whisper_listener_loads_small_en(mock_model_cls: MagicMock) -> None:
    mock_model_cls.return_value = MagicMock()
    listener = WhisperVoiceListener(
        {
            "stt_engine": "whisper",
            "whisper_model": "small",
            "whisper_language": "en",
            "whisper_device": "cpu",
            "whisper_compute_type": "int8",
        }
    )
    assert listener.engine_label == "faster-whisper (small.en)"
    mock_model_cls.assert_called_once_with("small.en", device="cpu", compute_type="int8")


@patch("faster_whisper.WhisperModel")
def test_whisper_transcribe_returns_text(mock_model_cls: MagicMock) -> None:
    segment = MagicMock()
    segment.text = "open file manager"
    model = MagicMock()
    model.transcribe.return_value = ([segment], None)
    mock_model_cls.return_value = model

    listener = WhisperVoiceListener(
        {
            "whisper_model": "small.en",
            "whisper_device": "cpu",
            "whisper_compute_type": "int8",
        }
    )
    pcm = (np.zeros(16000, dtype=np.int16)).tobytes()
    assert listener._transcribe(pcm) == "open file manager"
