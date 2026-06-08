"""faster-whisper phrase-at-a-time speech recognition."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from typing import Any

import sounddevice as sd

from core import console_ui
from core.listener.audio import (
    AudioPreroll,
    VoiceSetupError,
    input_device_ready,
    parse_audio_stream_retries,
    parse_input_device,
    pcm16le_rms,
    portaudio_errors,
    reset_audio_backend,
)

_STREAM_BLOCKSIZE = 4000


def _resolve_whisper_device(cfg_value: str) -> str:
    raw = (cfg_value or "auto").strip().lower()
    if raw in {"cpu", "cuda"}:
        return raw
    try:
        import ctranslate2  # type: ignore[import-untyped]

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _default_whisper_compute_type(device: str, cfg_value: str) -> str:
    raw = (cfg_value or "default").strip().lower()
    if raw != "default":
        return raw
    return "int8" if device == "cpu" else "float16"


def _normalize_whisper_model(model_name: str, language: str) -> str:
    """Prefer English-only checkpoints (smaller, faster) when language is English."""
    name = (model_name or "small.en").strip() or "small.en"
    lang = (language or "en").strip().lower()
    if lang.startswith("en") and "." not in name:
        return f"{name}.en"
    return name


class WhisperVoiceListener:
    """
    Phrase-at-a-time recognition with faster-whisper (OpenAI-style model).
    Install: ``pip install faster-whisper`` (and use a CUDA build of ctranslate2 for GPU).
    """

    def __init__(self, config: dict[str, Any]) -> None:
        try:
            from faster_whisper import WhisperModel  # type: ignore[import-untyped]
        except ImportError as exc:
            raise VoiceSetupError(
                "Whisper STT requires the `faster-whisper` package. From your venv run:\n"
                "  pip install faster-whisper\n"
                "Or switch config stt_engine back to \"vosk\"."
            ) from exc

        self.sample_rate = int(config.get("sample_rate", 16000))
        self._language = str(config.get("whisper_language", "en")).strip() or "en"
        self._model_name = _normalize_whisper_model(
            str(config.get("whisper_model", "small.en")),
            self._language,
        )
        device = _resolve_whisper_device(str(config.get("whisper_device", "auto")))
        compute_type = _default_whisper_compute_type(
            device, str(config.get("whisper_compute_type", "default"))
        )
        prompt = str(config.get("whisper_initial_prompt", "")).strip()
        self._initial_prompt = prompt or None
        self._utterance_end_silence = float(config.get("whisper_end_silence_sec", 0.85))
        self._max_utterance_sec = float(config.get("whisper_max_utterance_sec", 45.0))

        console_ui.emit(
            f"Loading faster-whisper {self._model_name!r} ({device}, {compute_type})… "
            "First run downloads the model (~460 MB for small.en).",
            style="cyan",
        )
        self._model = WhisperModel(
            self._model_name,
            device=device,
            compute_type=compute_type,
        )
        self._input_device = parse_input_device(config)
        self._audio_stream_retries = parse_audio_stream_retries(config)

    @property
    def engine_label(self) -> str:
        return f"faster-whisper ({self._model_name})"

    def _transcribe(self, pcm16_mono: bytes) -> str:
        min_bytes = int(self.sample_rate * 0.12) * 2
        if len(pcm16_mono) < min_bytes:
            return ""
        import numpy as np

        audio = np.frombuffer(pcm16_mono, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _info = self._model.transcribe(
            audio,
            language=self._language,
            beam_size=3,
            best_of=3,
            temperature=0.0,
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 400,
                "speech_pad_ms": 200,
            },
            condition_on_previous_text=False,
            compression_ratio_threshold=2.0,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.55,
            initial_prompt=self._initial_prompt,
        )
        return "".join(segment.text for segment in segments).strip()

    def listen_once(
        self,
        idle_timeout_sec: float | None = None,
        idle_rms_threshold: float = 550.0,
        idle_grace_sec: float = 1.25,
        echo_status: bool = True,
        *,
        on_speech_pause: Callable[[], None] | None = None,
        speech_pause_to_processing_sec: float = 0.55,
        cancel_event: threading.Event | None = None,
    ) -> str:
        audio_queue: queue.Queue[bytes] = queue.Queue()
        buffer = bytearray()
        preroll = AudioPreroll(self.sample_rate)
        preroll_merged = False
        start_mono = time.monotonic()
        last_voice_mono = start_mono
        saw_voice = False
        max_bytes = int(self.sample_rate * 2 * max(5.0, self._max_utterance_sec))
        pause_sent = False

        def callback(indata, frames, time_info, status):  # noqa: ANN001, ANN202
            nonlocal last_voice_mono, saw_voice, pause_sent
            if status:
                console_ui.emit_dim(f"[audio] {status}")
            raw = bytes(indata)
            audio_queue.put(raw)
            preroll.push(raw)
            if pcm16le_rms(raw) >= idle_rms_threshold:
                last_voice_mono = time.monotonic()
                saw_voice = True
                pause_sent = False

        if echo_status:
            console_ui.emit_listen_prompt()

        if not input_device_ready(self._input_device):
            reset_audio_backend()
            time.sleep(0.35)

        pa_errors = portaudio_errors()
        last_audio_exc: BaseException | None = None
        for attempt in range(self._audio_stream_retries):
            if attempt > 0:
                reset_audio_backend()
                time.sleep(0.2 + 0.2 * attempt)
                console_ui.emit(
                    f"Microphone stream failed ({last_audio_exc}); "
                    f"retry {attempt + 1}/{self._audio_stream_retries}…",
                    style="yellow",
                )
            try:
                with sd.RawInputStream(
                    samplerate=self.sample_rate,
                    blocksize=_STREAM_BLOCKSIZE,
                    dtype="int16",
                    channels=1,
                    callback=callback,
                    device=self._input_device,
                ):
                    while True:
                        if cancel_event is not None and cancel_event.is_set():
                            return ""
                        now = time.monotonic()
                        if idle_timeout_sec is not None and idle_timeout_sec > 0:
                            if (
                                now - start_mono >= idle_grace_sec
                                and now - last_voice_mono >= idle_timeout_sec
                            ):
                                if saw_voice and buffer:
                                    if on_speech_pause and not pause_sent:
                                        on_speech_pause()
                                        pause_sent = True
                                    text = self._transcribe(bytes(buffer))
                                    buffer.clear()
                                    saw_voice = False
                                    start_mono = now
                                    last_voice_mono = now
                                    return text
                                if not saw_voice:
                                    return ""
                        if saw_voice and (now - last_voice_mono >= self._utterance_end_silence):
                            if on_speech_pause and not pause_sent:
                                on_speech_pause()
                                pause_sent = True
                            text = self._transcribe(bytes(buffer))
                            buffer.clear()
                            saw_voice = False
                            last_voice_mono = now
                            start_mono = now
                            if text:
                                return text
                        try:
                            data = audio_queue.get(timeout=0.2)
                        except queue.Empty:
                            now = time.monotonic()
                            if (
                                on_speech_pause
                                and not pause_sent
                                and saw_voice
                                and speech_pause_to_processing_sec > 0
                                and now - last_voice_mono >= speech_pause_to_processing_sec
                                and now - last_voice_mono < self._utterance_end_silence
                            ):
                                on_speech_pause()
                                pause_sent = True
                            continue
                        rms = pcm16le_rms(data)
                        voice_now = rms >= idle_rms_threshold
                        if voice_now and not preroll_merged:
                            lead_in = preroll.snapshot()
                            if lead_in:
                                buffer.extend(lead_in)
                            preroll_merged = True
                            preroll.clear()
                        if saw_voice or rms >= idle_rms_threshold * 0.35:
                            buffer.extend(data)
                            if len(buffer) > max_bytes:
                                del buffer[: len(buffer) - max_bytes // 2]
                        elif not saw_voice and len(buffer) > self.sample_rate * 2 * 2:
                            buffer.clear()
            except pa_errors as exc:
                last_audio_exc = exc
                continue
        assert last_audio_exc is not None
        raise last_audio_exc
