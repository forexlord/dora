from __future__ import annotations

import logging
import sys
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.win_com import SapiSpeechSynthesizer

logger = logging.getLogger("dora.tts")


class TextToSpeech:
    def __init__(
        self,
        enabled: bool = True,
        rate: int = 0,
        volume: int = 70,
        preferred_voice: str = "zira",
    ) -> None:
        self.enabled = enabled
        self.rate = rate
        self.volume = max(0, min(100, int(volume)))
        self.preferred_voice = (preferred_voice or "").strip().lower()
        self._engine: SapiSpeechSynthesizer | None = None
        self._thread: threading.Thread | None = None

    def _get_engine(self) -> SapiSpeechSynthesizer:
        if self._engine is None:
            from core.win_com import SapiSpeechSynthesizer

            self._engine = SapiSpeechSynthesizer(
                rate=self.rate,
                volume=self.volume,
                preferred_voice=self.preferred_voice,
            )
        return self._engine

    def stop(self) -> None:
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                logger.exception("Failed to stop TTS engine")

    def speak_async(
        self,
        text: str,
        *,
        cancel_event: threading.Event | None = None,
    ) -> threading.Thread:
        thread = threading.Thread(
            target=self.speak,
            args=(text,),
            kwargs={"cancel_event": cancel_event},
            name="dora-tts",
            daemon=True,
        )
        self._thread = thread
        thread.start()
        return thread

    def speak(
        self,
        text: str,
        *,
        cancel_event: threading.Event | None = None,
    ) -> None:
        if not self.enabled:
            return
        message = (text or "").strip()
        if not message:
            return
        if cancel_event is not None and cancel_event.is_set():
            return
        if sys.platform != "win32":
            logger.warning("TTS is only supported on Windows; skipped: %r", message[:80])
            return
        try:
            self._get_engine().speak(message)
        except Exception:
            logger.exception("TTS speak failed")
