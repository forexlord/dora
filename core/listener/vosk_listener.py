"""Vosk streaming speech recognition."""

from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path

import sounddevice as sd
from vosk import KaldiRecognizer, Model

from core import console_ui
from core.listener.audio import (
    AudioPreroll,
    VoiceSetupError,
    input_device_ready,
    pcm16le_rms,
    portaudio_errors,
    reset_audio_backend,
)

_STREAM_BLOCKSIZE = 4000


class VoiceListener:
    """Streaming STT with Vosk (offline). Larger models in config sound much better than *-small-*."""

    def __init__(
        self,
        model_path: str,
        sample_rate: int = 16000,
        *,
        input_device: int | None = None,
        audio_stream_retries: int = 4,
    ) -> None:
        model_dir = self._resolve_model_dir(Path(model_path))
        self._validate_model_dir(model_dir)
        self.sample_rate = sample_rate
        self.model_dir = model_dir
        self._input_device = input_device
        self._audio_stream_retries = audio_stream_retries
        try:
            self.model = Model(str(model_dir))
        except Exception as exc:  # pragma: no cover
            raise VoiceSetupError(
                "Vosk failed to load the model from "
                f"'{model_path}'. Make sure this path points to the extracted "
                "model directory containing folders like 'am', 'conf', and 'graph'."
            ) from exc

    @property
    def engine_label(self) -> str:
        return f"Vosk ({self.model_dir.name})"

    def _resolve_model_dir(self, model_dir: Path) -> Path:
        if not model_dir.exists() or not model_dir.is_dir():
            return model_dir
        expected_items = {"am", "conf", "graph"}
        present_items = {p.name for p in model_dir.iterdir()}
        if expected_items.issubset(present_items):
            return model_dir
        subdirs = [p for p in model_dir.iterdir() if p.is_dir()]
        candidate = next(
            (
                p
                for p in subdirs
                if expected_items.issubset({c.name for c in p.iterdir()})
            ),
            None,
        )
        return candidate or model_dir

    def _validate_model_dir(self, model_dir: Path) -> None:
        if not model_dir.exists():
            raise VoiceSetupError(
                f"Vosk model path not found: '{model_dir}'. "
                "Update config.json -> vosk_model_path."
            )
        if not model_dir.is_dir():
            raise VoiceSetupError(f"Vosk model path is not a directory: '{model_dir}'.")

        expected_items = {"am", "conf", "graph"}
        present_items = {p.name for p in model_dir.iterdir()}
        if expected_items.issubset(present_items):
            return

        raise VoiceSetupError(
            f"'{model_dir}' does not look like a Vosk model directory. "
            "Expected subfolders: 'am', 'conf', 'graph'."
        )

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
        """
        Block until Vosk finalizes a non-empty utterance, or (if idle_timeout_sec set)
        until that many seconds pass with no voice-level audio (session idle).
        """
        audio_queue: queue.Queue[bytes] = queue.Queue()
        recognizer = KaldiRecognizer(self.model, self.sample_rate)
        preroll = AudioPreroll(self.sample_rate)
        preroll_sent = False
        start_mono = time.monotonic()
        last_voice_mono = start_mono
        pause_state = {"ever_voice": False, "pause_sent": False}

        def callback(indata, frames, time_info, status):  # noqa: ANN001, ANN202
            nonlocal last_voice_mono
            if status:
                console_ui.emit_dim(f"[audio] {status}")
            raw = bytes(indata)
            audio_queue.put(raw)
            preroll.push(raw)
            if pcm16le_rms(raw) >= idle_rms_threshold:
                last_voice_mono = time.monotonic()
                pause_state["ever_voice"] = True
                pause_state["pause_sent"] = False

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
                        if idle_timeout_sec is not None and idle_timeout_sec > 0:
                            now = time.monotonic()
                            if (
                                now - start_mono >= idle_grace_sec
                                and now - last_voice_mono >= idle_timeout_sec
                            ):
                                final = json.loads(recognizer.FinalResult())
                                text = final.get("text", "").strip()
                                if text:
                                    return text
                                partial = json.loads(recognizer.PartialResult())
                                tail = partial.get("partial", "").strip()
                                if tail:
                                    return tail
                                return ""
                        try:
                            data = audio_queue.get(timeout=0.2)
                        except queue.Empty:
                            now = time.monotonic()
                            if (
                                on_speech_pause
                                and not pause_state["pause_sent"]
                                and pause_state["ever_voice"]
                                and speech_pause_to_processing_sec > 0
                                and now - last_voice_mono >= speech_pause_to_processing_sec
                            ):
                                on_speech_pause()
                                pause_state["pause_sent"] = True
                            continue
                        if (
                            not preroll_sent
                            and pcm16le_rms(data) >= idle_rms_threshold
                        ):
                            lead_in = preroll.snapshot()
                            preroll_sent = True
                            preroll.clear()
                            if lead_in and recognizer.AcceptWaveform(lead_in):
                                if (
                                    on_speech_pause
                                    and not pause_state["pause_sent"]
                                    and pause_state["ever_voice"]
                                ):
                                    on_speech_pause()
                                    pause_state["pause_sent"] = True
                                result = json.loads(recognizer.Result())
                                text = result.get("text", "").strip()
                                if text:
                                    return text
                            continue
                        if recognizer.AcceptWaveform(data):
                            if (
                                on_speech_pause
                                and not pause_state["pause_sent"]
                                and pause_state["ever_voice"]
                            ):
                                on_speech_pause()
                                pause_state["pause_sent"] = True
                            result = json.loads(recognizer.Result())
                            text = result.get("text", "").strip()
                            if text:
                                return text
            except pa_errors as exc:
                last_audio_exc = exc
                continue
        assert last_audio_exc is not None
        raise last_audio_exc
