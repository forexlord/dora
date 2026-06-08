"""Speech listener factory and public exports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.config import DoraConfig
from core.listener.audio import (
    VoiceSetupError,
    parse_audio_stream_retries,
    parse_input_device,
    reset_audio_backend,
)
from core.listener.vosk_listener import VoiceListener
from core.listener.whisper_listener import WhisperVoiceListener


def _config_dict(config: DoraConfig | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(config, DoraConfig):
        return config.to_dict()
    return dict(config)


def create_speech_listener(
    config: DoraConfig | Mapping[str, Any],
) -> VoiceListener | WhisperVoiceListener:
    data = _config_dict(config)
    engine = str(data.get("stt_engine", "whisper")).strip().lower()
    if engine == "whisper":
        return WhisperVoiceListener(data)
    if engine not in {"", "vosk"}:
        raise VoiceSetupError(
            f'Unknown stt_engine {engine!r}. Use "vosk" or "whisper".'
        )
    return VoiceListener(
        model_path=str(data["vosk_model_path"]),
        sample_rate=int(data.get("sample_rate", 16000)),
        input_device=parse_input_device(data),
        audio_stream_retries=parse_audio_stream_retries(data),
    )


__all__ = [
    "VoiceListener",
    "VoiceSetupError",
    "WhisperVoiceListener",
    "create_speech_listener",
    "reset_audio_backend",
]
