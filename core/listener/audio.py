"""Shared microphone / PortAudio helpers for speech listeners."""

from __future__ import annotations

import logging
from typing import Any

import sounddevice as sd

from core import console_ui

logger = logging.getLogger("dora.audio")


class VoiceSetupError(Exception):
    """Raised when local speech model setup is invalid."""


def portaudio_errors() -> tuple[type[BaseException], ...]:
    err = getattr(sd, "PortAudioError", None)
    return (OSError,) if err is None else (OSError, err)


def reset_audio_backend() -> None:
    """
    Reinitialize PortAudio. Helps after sleep/resume or when the default mic
    disappears briefly (Windows USB / Bluetooth stack).
    """
    try:
        sd._terminate()  # noqa: SLF001
    except Exception:
        pass
    try:
        sd._initialize()  # noqa: SLF001
    except Exception:
        pass


def parse_input_device(config: dict[str, Any]) -> int | None:
    raw = config.get("audio_input_device")
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if text in {"", "default", "auto", "none"}:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        console_ui.emit(
            f"Invalid audio_input_device {raw!r}; using system default.",
            style="yellow",
        )
        logger.warning("Invalid audio_input_device %r; using system default.", raw)
        return None


def parse_audio_stream_retries(config: dict[str, Any]) -> int:
    try:
        count = int(config.get("audio_stream_retries", 4))
    except (TypeError, ValueError):
        return 4
    return max(1, min(count, 12))


def input_device_ready(device: int | None) -> bool:
    try:
        if device is not None:
            info = sd.query_devices(device)
        else:
            info = sd.query_devices(kind="input")
        return int(info.get("max_input_channels") or 0) > 0
    except Exception:
        return False


class AudioPreroll:
    """Keep the last N seconds of mic audio so utterance onset is not clipped."""

    def __init__(self, sample_rate: int, *, seconds: float = 0.6) -> None:
        self._max_bytes = max(1, int(sample_rate * 2 * seconds))
        self._buf = bytearray()

    def push(self, chunk: bytes) -> None:
        if not chunk:
            return
        self._buf.extend(chunk)
        overflow = len(self._buf) - self._max_bytes
        if overflow > 0:
            del self._buf[:overflow]

    def snapshot(self) -> bytes:
        return bytes(self._buf)

    def clear(self) -> None:
        self._buf.clear()


def pcm16le_rms(raw: bytes) -> float:
    count = len(raw) // 2
    if count <= 0:
        return 0.0
    acc = 0.0
    for i in range(0, len(raw), 2):
        value = int.from_bytes(raw[i : i + 2], "little", signed=True)
        acc += float(value) * float(value)
    return (acc / count) ** 0.5
