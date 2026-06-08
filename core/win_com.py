"""Native Windows COM/ctypes helpers (avoid spawning PowerShell per action)."""

from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes
from typing import Any

if sys.platform == "win32":
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
else:
    kernel32 = None  # type: ignore[assignment]


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_byte),
        ("BatteryFlag", ctypes.c_byte),
        ("BatteryLifePercent", ctypes.c_byte),
        ("SystemStatusFlag", ctypes.c_byte),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


def get_battery_status_native() -> tuple[bool, str]:
    """Read battery level via GetSystemPowerStatus (no PowerShell)."""
    if kernel32 is None:
        return False, "Battery status is only supported on Windows."
    status = SYSTEM_POWER_STATUS()
    if not kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return False, "Could not read battery status from Windows."

    pct = int(status.BatteryLifePercent)
    if pct == 255:
        return (
            False,
            "This PC does not report a battery, or charge level is not available "
            "(common on desktops).",
        )

    plugged = status.ACLineStatus == 1
    msg = f"Your battery is at {pct} percent"
    if plugged:
        msg += ", and the power cable is connected"
        if status.BatteryFlag == 1:
            msg += ", and it is charging"
        elif pct >= 95:
            msg += ", and it looks fully charged"
    else:
        msg += ", and you are running on battery power"
        if status.BatteryFlag in {2, 4}:
            msg += ", and the charge is low"
    return True, msg + "."


class SapiSpeechSynthesizer:
    """Windows SAPI.SpVoice TTS via comtypes (no PowerShell per utterance)."""

    def __init__(
        self,
        *,
        rate: int = 0,
        volume: int = 70,
        preferred_voice: str = "zira",
    ) -> None:
        self._rate = rate
        self._volume = max(0, min(100, int(volume)))
        self._preferred_voice = (preferred_voice or "").strip().lower()
        self._lock = threading.Lock()
        self._voice: Any = None

    def _ensure_voice(self) -> Any:
        if self._voice is not None:
            return self._voice
        import comtypes.client  # lazy: only on Windows with comtypes installed

        voice = comtypes.client.CreateObject("SAPI.SpVoice")
        voice.Rate = self._rate
        voice.Volume = self._volume
        if self._preferred_voice:
            tokens = voice.GetVoices()
            for i in range(tokens.Count):
                token = tokens.Item(i)
                name = str(token.GetDescription()).lower()
                if self._preferred_voice in name:
                    voice.Voice = token
                    break
        self._voice = voice
        return voice

    def speak(self, text: str) -> None:
        message = (text or "").strip()
        if not message:
            return
        with self._lock:
            voice = self._ensure_voice()
            voice.Speak(message)

    def stop(self) -> None:
        with self._lock:
            if self._voice is None:
                return
            try:
                self._voice.Speak("", 2)  # SVSFPurgeBeforeSpeak
            except Exception:
                pass
