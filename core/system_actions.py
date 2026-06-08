from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_HOTSPOT_SETTINGS_MSG = (
    "Mobile hotspot is controlled in Windows Settings → Network & internet → "
    "Mobile hotspot. Open Settings and toggle it there."
)


def _endpoint_volume() -> tuple[Any | None, str]:
    """
    Default playback (multimedia) endpoint volume. pycaw 2025+ exposes this via
    AudioDevice.EndpointVolume (not AudioDevice.Activate).
    """
    try:
        from pycaw.pycaw import AudioUtilities
    except ImportError as exc:
        return None, f"Install pycaw and comtypes in the same venv you use to run the app: {exc}"

    try:
        dev = AudioUtilities.GetSpeakers()
        if dev is None:
            return None, "No default playback device."
        return dev.EndpointVolume, ""
    except Exception as exc:
        return None, f"Volume COM error (try running from venv Python): {exc}"


def get_volume_percent() -> tuple[bool, float | None, str]:
    vol, err = _endpoint_volume()
    if vol is None:
        return False, None, err or "Could not open volume control."
    try:
        scalar = float(vol.GetMasterVolumeLevelScalar())
        return True, round(scalar * 100.0, 1), ""
    except Exception as exc:
        return False, None, str(exc)


def get_mute_state() -> tuple[bool, bool | None, str]:
    vol, err = _endpoint_volume()
    if vol is None:
        return False, None, err or "Could not open volume control."
    try:
        return True, bool(vol.GetMute()), ""
    except Exception as exc:
        return False, None, str(exc)


def _volume_level_label(percent: int) -> str:
    if percent <= 0:
        return "very low"
    if percent < 25:
        return "low"
    if percent < 70:
        return "medium"
    if percent < 90:
        return "high"
    return "very high"


def get_volume_status() -> tuple[bool, str]:
    """Read real master volume and mute state from Windows."""
    ok_p, pct, err_p = get_volume_percent()
    if not ok_p or pct is None:
        return False, err_p or "Could not read volume level."
    ok_m, muted, err_m = get_mute_state()
    if not ok_m or muted is None:
        return False, err_m or "Could not read mute state."

    pct_i = int(round(pct))
    label = _volume_level_label(pct_i)

    if muted:
        return (
            True,
            f"Your volume is muted. The level is set to about {pct_i} percent, "
            f"but audio is off. Say unmute when you want sound back.",
        )
    return (
        True,
        f"Your volume is at {pct_i} percent, which is {label}. Audio is not muted.",
    )


def set_volume_percent(percent: float) -> tuple[bool, str]:
    vol, err = _endpoint_volume()
    if vol is None:
        return False, err or "Could not open volume control."
    try:
        level = max(0.0, min(1.0, percent / 100.0))
        vol.SetMasterVolumeLevelScalar(level, None)
        return True, f"Volume set to about {int(round(level * 100))} percent."
    except Exception as exc:
        return False, f"Volume error: {exc}"


def adjust_volume_percent(delta: float) -> tuple[bool, str]:
    ok, current, err = get_volume_percent()
    if not ok or current is None:
        return False, err or "Could not read volume."
    new_p = max(0.0, min(100.0, current + delta))
    ok2, msg = set_volume_percent(new_p)
    if not ok2:
        return False, msg
    return True, f"Volume was {current:.0f} percent; {msg}"


def set_mute(muted: bool) -> tuple[bool, str]:
    vol, err = _endpoint_volume()
    if vol is None:
        return False, err or "Could not open volume control."
    try:
        vol.SetMute(1 if muted else 0, None)
        return True, "Muted." if muted else "Unmuted."
    except Exception as exc:
        return False, str(exc)


def get_brightness_percent() -> tuple[bool, int | None, str]:
    from core.win_wmi import get_brightness_percent_wmi

    return get_brightness_percent_wmi()


def set_brightness_percent(percent: int) -> tuple[bool, str]:
    from core.win_wmi import set_brightness_percent_wmi

    return set_brightness_percent_wmi(percent)


def adjust_brightness_percent(delta: float) -> tuple[bool, str]:
    ok, cur, err = get_brightness_percent()
    if not ok or cur is None:
        return False, err
    return set_brightness_percent(int(round(cur + delta)))


def wifi_set(enabled: bool) -> tuple[bool, str]:
    from core.win_netsh import wifi_set_netsh

    return wifi_set_netsh(enabled)


def wifi_toggle() -> tuple[bool, str]:
    from core.win_netsh import wifi_toggle_netsh

    return wifi_toggle_netsh()


def hotspot_set(enabled: bool) -> tuple[bool, str]:
    del enabled
    return False, _HOTSPOT_SETTINGS_MSG


def hotspot_toggle() -> tuple[bool, str]:
    return False, _HOTSPOT_SETTINGS_MSG


def get_battery_status() -> tuple[bool, str]:
    """Read the real battery level from Windows (not the LLM)."""
    from core.win_com import get_battery_status_native

    return get_battery_status_native()


def apply_system_intent(intent: Mapping[str, Any]) -> tuple[bool, str]:
    """Run a parsed system-control intent. Returns (ok, message_for_user)."""
    itype = str(intent.get("type", "")).strip().lower()
    if itype == "volume_relative":
        d = intent.get("delta_percent")
        if isinstance(d, int | float):
            return adjust_volume_percent(float(d))
        return False, "Missing volume change amount."
    if itype == "volume_set":
        p = intent.get("percent")
        if isinstance(p, int | float):
            return set_volume_percent(float(p))
        return False, "Missing volume level."
    if itype == "volume_mute":
        return set_mute(True)
    if itype == "volume_unmute":
        return set_mute(False)
    if itype == "brightness_relative":
        d = intent.get("delta_percent")
        if isinstance(d, int | float):
            return adjust_brightness_percent(float(d))
        return False, "Missing brightness change amount."
    if itype == "brightness_set":
        p = intent.get("percent")
        if isinstance(p, int | float):
            return set_brightness_percent(int(round(float(p))))
        return False, "Missing brightness level."
    if itype == "wifi":
        act = str(intent.get("action", "toggle")).strip().lower()
        if act == "on":
            return wifi_set(True)
        if act == "off":
            return wifi_set(False)
        return wifi_toggle()
    if itype == "hotspot":
        return hotspot_toggle()
    if itype == "battery_status":
        return get_battery_status()
    if itype == "volume_status":
        return get_volume_status()
    return False, "Unknown system action."
