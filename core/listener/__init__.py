"""Speech listener factory and public exports."""

from __future__ import annotations

from typing import Any

from core.listener.audio import (
    VoiceSetupError,
    parse_audio_stream_retries,
    parse_input_device,
    reset_audio_backend,
)
from core.listener.vosk_listener import VoiceListener
from core.listener.whisper_listener import WhisperVoiceListener


def create_speech_listener(config: dict[str, Any]) -> VoiceListener | WhisperVoiceListener:
    engine = str(config.get("stt_engine", "vosk")).strip().lower()
    if engine == "whisper":
        return WhisperVoiceListener(config)
    if engine not in {"", "vosk"}:
        raise VoiceSetupError(
            f'Unknown stt_engine {engine!r}. Use "vosk" or "whisper".'
        )
    return VoiceListener(
        model_path=str(config["vosk_model_path"]),
        sample_rate=int(config.get("sample_rate", 16000)),
        input_device=parse_input_device(config),
        audio_stream_retries=parse_audio_stream_retries(config),
    )


__all__ = [
    "VoiceListener",
    "VoiceSetupError",
    "WhisperVoiceListener",
    "create_speech_listener",
    "reset_audio_backend",
]
