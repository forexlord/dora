from __future__ import annotations

import subprocess
import threading
import time
from typing import Any

from core.win_subprocess import popen_no_console


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
        self._proc: subprocess.Popen[Any] | None = None

    def stop(self) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
        except OSError:
            pass
        try:
            proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass

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
        safe = message.replace("'", "''")
        voice_select = ""
        if self.preferred_voice:
            safe_voice = self.preferred_voice.replace("'", "''")
            voice_select = (
                "$voice = $speak.GetInstalledVoices() | "
                "ForEach-Object { $_.VoiceInfo.Name } | "
                f"Where-Object {{ $_.ToLower().Contains('{safe_voice}') }} | "
                "Select-Object -First 1; "
                "if ($voice) { $speak.SelectVoice($voice) }; "
            )
        cmd = (
            "Add-Type -AssemblyName System.Speech; "
            "$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$speak.Rate = {self.rate}; "
            f"$speak.Volume = {self.volume}; "
            f"{voice_select}"
            f"$speak.Speak('{safe}')"
        )
        proc = popen_no_console(
            ["powershell", "-NoProfile", "-Command", cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._proc = proc
        try:
            while proc.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    self.stop()
                    return
                time.sleep(0.05)
        finally:
            if self._proc is proc:
                self._proc = None
