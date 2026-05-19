from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import sounddevice as sd
from vosk import KaldiRecognizer, Model


def _portaudio_errors() -> tuple[type[BaseException], ...]:
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


def _parse_input_device(config: dict[str, Any]) -> int | None:
    raw = config.get("audio_input_device")
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in {"", "default", "auto", "none"}:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        print(f"[yellow]Invalid audio_input_device {raw!r}; using system default.[/yellow]")
        return None


def _parse_audio_stream_retries(config: dict[str, Any]) -> int:
    try:
        n = int(config.get("audio_stream_retries", 4))
    except (TypeError, ValueError):
        return 4
    return max(1, min(n, 12))


def _input_device_ready(device: int | None) -> bool:
    try:
        if device is not None:
            info = sd.query_devices(device)
        else:
            info = sd.query_devices(kind="input")
        return int(info.get("max_input_channels") or 0) > 0
    except Exception:
        return False


def _pcm16le_rms(raw: bytes) -> float:
    n = len(raw) // 2
    if n <= 0:
        return 0.0
    acc = 0.0
    for i in range(0, len(raw), 2):
        v = int.from_bytes(raw[i : i + 2], "little", signed=True)
        acc += float(v) * float(v)
    return (acc / n) ** 0.5


class VoiceSetupError(Exception):
    """Raised when local speech model setup is invalid."""


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

        If ``on_speech_pause`` is set, it is called once after speech energy drops for
        ``speech_pause_to_processing_sec`` so the UI can show "processing" before the
        final Kaldi result is ready.
        """
        audio_queue: queue.Queue[bytes] = queue.Queue()
        recognizer = KaldiRecognizer(self.model, self.sample_rate)
        start_mono = time.monotonic()
        last_voice_mono = start_mono
        pause_state = {"ever_voice": False, "pause_sent": False}

        def callback(indata, frames, time_info, status):  # noqa: ANN001, ANN202
            nonlocal last_voice_mono
            if status:
                print(f"[audio] {status}")
            raw = bytes(indata)
            audio_queue.put(raw)
            if _pcm16le_rms(raw) >= idle_rms_threshold:
                last_voice_mono = time.monotonic()
                pause_state["ever_voice"] = True
                pause_state["pause_sent"] = False

        if echo_status:
            print("Listening... speak now.")

        if not _input_device_ready(self._input_device):
            reset_audio_backend()
            time.sleep(0.35)

        pa_errors = _portaudio_errors()
        last_audio_exc: BaseException | None = None
        for attempt in range(self._audio_stream_retries):
            if attempt > 0:
                reset_audio_backend()
                time.sleep(0.2 + 0.2 * attempt)
                print(
                    f"[yellow]Microphone stream failed ({last_audio_exc}); "
                    f"retry {attempt + 1}/{self._audio_stream_retries}…[/yellow]"
                )
            try:
                with sd.RawInputStream(
                    samplerate=self.sample_rate,
                    blocksize=8000,
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
        self._model_name = str(config.get("whisper_model", "small")).strip() or "small"
        device = _resolve_whisper_device(str(config.get("whisper_device", "auto")))
        compute_type = _default_whisper_compute_type(
            device, str(config.get("whisper_compute_type", "default"))
        )
        self._language = str(config.get("whisper_language", "en")).strip() or "en"
        prompt = str(config.get("whisper_initial_prompt", "")).strip()
        self._initial_prompt = prompt or None
        self._utterance_end_silence = float(config.get("whisper_end_silence_sec", 0.85))
        self._max_utterance_sec = float(config.get("whisper_max_utterance_sec", 45.0))

        print(f"[cyan]Loading Whisper model[/cyan] {self._model_name!r} ({device}, {compute_type})…")
        self._model = WhisperModel(
            self._model_name,
            device=device,
            compute_type=compute_type,
        )
        self._input_device = _parse_input_device(config)
        self._audio_stream_retries = _parse_audio_stream_retries(config)

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
            beam_size=5,
            vad_filter=True,
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
        start_mono = time.monotonic()
        last_voice_mono = start_mono
        saw_voice = False
        max_bytes = int(self.sample_rate * 2 * max(5.0, self._max_utterance_sec))
        pause_sent = False

        def callback(indata, frames, time_info, status):  # noqa: ANN001, ANN202
            nonlocal last_voice_mono, saw_voice, pause_sent
            if status:
                print(f"[audio] {status}")
            raw = bytes(indata)
            audio_queue.put(raw)
            if _pcm16le_rms(raw) >= idle_rms_threshold:
                last_voice_mono = time.monotonic()
                saw_voice = True
                pause_sent = False

        if echo_status:
            print("Listening... speak now.")

        if not _input_device_ready(self._input_device):
            reset_audio_backend()
            time.sleep(0.35)

        pa_errors = _portaudio_errors()
        last_audio_exc: BaseException | None = None
        for attempt in range(self._audio_stream_retries):
            if attempt > 0:
                reset_audio_backend()
                time.sleep(0.2 + 0.2 * attempt)
                print(
                    f"[yellow]Microphone stream failed ({last_audio_exc}); "
                    f"retry {attempt + 1}/{self._audio_stream_retries}…[/yellow]"
                )
            try:
                with sd.RawInputStream(
                    samplerate=self.sample_rate,
                    blocksize=8000,
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
                        rms = _pcm16le_rms(data)
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
        input_device=_parse_input_device(config),
        audio_stream_retries=_parse_audio_stream_retries(config),
    )
