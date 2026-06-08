import pytest

from core.listener import VoiceSetupError, create_speech_listener
from core.listener.audio import VoiceSetupError as AudioVoiceSetupError
from unittest.mock import patch


def test_create_speech_listener_vosk() -> None:
    with patch("core.listener.VoiceListener") as mock_vosk:
        create_speech_listener({"vosk_model_path": "models/vosk", "stt_engine": "vosk"})
        mock_vosk.assert_called_once()


def test_create_speech_listener_whisper() -> None:
    with patch("core.listener.WhisperVoiceListener") as mock_whisper:
        create_speech_listener({"stt_engine": "whisper"})
        mock_whisper.assert_called_once()


def test_create_speech_listener_unknown_engine() -> None:
    with pytest.raises(VoiceSetupError):
        create_speech_listener({"stt_engine": "dragon", "vosk_model_path": "m"})


def test_voice_setup_error_exported() -> None:
    assert VoiceSetupError is AudioVoiceSetupError
