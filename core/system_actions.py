from __future__ import annotations

import json
from typing import Any, Mapping

from core.win_subprocess import run_no_console


def _run_ps(script: str, timeout: int = 25) -> tuple[int, str, str]:
    result = run_no_console(
        ["powershell", "-NoProfile", "-STA", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    return result.returncode, out, err


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
    script = (
        "$b = Get-WmiObject -Namespace root\\wmi -Class WmiMonitorBrightness "
        "-ErrorAction SilentlyContinue | Select-Object -First 1; "
        "if ($b) { $b.CurrentBrightness } else { '' }"
    )
    code, out, err = _run_ps(script)
    if not out.strip():
        return False, None, (err or "Brightness WMI not available on this display (common on desktops).")
    try:
        return True, int(out.splitlines()[-1].strip()), ""
    except ValueError:
        return False, None, "Could not parse brightness."


def set_brightness_percent(percent: int) -> tuple[bool, str]:
    level = max(0, min(100, int(percent)))
    script = (
        "$m = Get-WmiObject -Namespace root\\wmi -Class WmiMonitorBrightnessMethods "
        "-ErrorAction SilentlyContinue | Select-Object -First 1; "
        f"if ($m) {{ $m.WmiSetBrightness(1, [byte]{level}); 'ok' }} else {{ '' }}"
    )
    code, out, err = _run_ps(script)
    if "ok" in out.splitlines()[-1].strip().lower() or "ok" in out:
        return True, f"Brightness set to about {level} percent."
    return False, err or out or "Could not set brightness (often laptop-only)."


def adjust_brightness_percent(delta: float) -> tuple[bool, str]:
    ok, cur, err = get_brightness_percent()
    if not ok or cur is None:
        return False, err
    return set_brightness_percent(int(round(cur + delta)))


_WIFI_MATCH = "Wi-Fi|Wireless|WLAN|802.11|WiFi"


def wifi_set(enabled: bool) -> tuple[bool, str]:
    onoff = "on" if enabled else "off"
    script = (
        f"$a = Get-NetAdapter | Where-Object {{ $_.InterfaceDescription -match '{_WIFI_MATCH}' }} "
        "| Select-Object -First 1; "
        "if (-not $a) { Write-Output 'ERR_NO_ADAPTER'; exit 1 }; "
        f"if ('{onoff}' -eq 'on') {{ Enable-NetAdapter -Name $a.Name -Confirm:$false }} "
        f"else {{ Disable-NetAdapter -Name $a.Name -Confirm:$false }}; "
        f"Write-Output 'WIFI_{onoff.upper()}'"
    )
    code, out, err = _run_ps(script)
    if "WIFI_ON" in out:
        return True, "Wi-Fi turned on."
    if "WIFI_OFF" in out:
        return True, "Wi-Fi turned off."
    if "ERR_NO_ADAPTER" in out:
        return False, "No Wi-Fi adapter found."
    return False, (err or out or "Wi-Fi command failed (try running as administrator).")


def wifi_toggle() -> tuple[bool, str]:
    script = (
        f"$a = Get-NetAdapter | Where-Object {{ $_.InterfaceDescription -match '{_WIFI_MATCH}' }} "
        "| Select-Object -First 1; "
        "if (-not $a) { Write-Output 'ERR_NO_ADAPTER'; exit 1 }; "
        "if ($a.Status -eq 'Up') { Disable-NetAdapter -Name $a.Name -Confirm:$false; "
        "Write-Output 'WIFI_OFF' } "
        "else { Enable-NetAdapter -Name $a.Name -Confirm:$false; Write-Output 'WIFI_ON' }"
    )
    code, out, err = _run_ps(script)
    if "WIFI_ON" in out:
        return True, "Wi-Fi is now on."
    if "WIFI_OFF" in out:
        return True, "Wi-Fi is now off."
    if "ERR_NO_ADAPTER" in out:
        return False, "No Wi-Fi adapter found."
    return False, (err or out or "Could not toggle Wi-Fi.")


def hotspot_set(enabled: bool) -> tuple[bool, str]:
    """
    Best-effort: legacy hosted network. Many PCs use Settings → Mobile hotspot instead.
    """
    if enabled:
        script = (
            "$o = netsh wlan start hostednetwork 2>&1 | Out-String; "
            "if ($LASTEXITCODE -eq 0) { Write-Output 'HOTSPOT_OK' } "
            "else { $o2 = netsh wlan set hostednetwork mode=allow 2>&1 | Out-String; "
            "netsh wlan start hostednetwork 2>&1 | Out-Null; "
            "if ($LASTEXITCODE -eq 0) { Write-Output 'HOTSPOT_OK' } else { Write-Output 'HOTSPOT_FAIL' } }"
        )
    else:
        script = (
            "netsh wlan stop hostednetwork 2>&1 | Out-Null; "
            "if ($LASTEXITCODE -eq 0) { Write-Output 'HOTSPOT_OK' } else { Write-Output 'HOTSPOT_FAIL' }"
        )
    code, out, err = _run_ps(script, timeout=25)
    if "HOTSPOT_OK" in out:
        return True, "Hotspot command completed (legacy hosted network)."
    return (
        False,
        "Mobile hotspot is not available via netsh on this PC. "
        "Use Settings → Network & internet → Mobile hotspot.",
    )


def get_battery_status() -> tuple[bool, str]:
    """
    Read the real battery level from Windows (not the LLM).
    Uses System.Windows.Forms.PowerStatus on the local machine.
    """
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$ps = [System.Windows.Forms.SystemInformation]::PowerStatus; "
        "$raw = [double]$ps.BatteryLifePercent; "
        "$pct = if ($raw -ge 0 -and $raw -le 1) { [int][math]::Round($raw * 100) } "
        "elseif ($raw -ge 0 -and $raw -le 100) { [int][math]::Round($raw) } else { -1 }; "
        "$plugged = ($ps.PowerLineStatus.ToString() -eq 'Online'); "
        "$chg = $ps.BatteryChargeStatus.ToString(); "
        "@{ percent = $pct; plugged = $plugged; charge_status = $chg } | ConvertTo-Json -Compress"
    )
    code, out, err = _run_ps(script, timeout=12)
    if code != 0 or not out:
        return False, err or "Could not read battery status from Windows."
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return False, "Could not parse battery status from Windows."

    pct = int(data.get("percent", -1))
    if pct < 0 or pct > 100:
        return (
            False,
            "This PC does not report a battery, or charge level is not available "
            "(common on desktops).",
        )

    plugged = bool(data.get("plugged", False))
    charge = str(data.get("charge_status", "")).strip()

    msg = f"Your battery is at {pct} percent"
    if plugged:
        msg += ", and the power cable is connected"
        low_chg = charge.lower()
        if "charging" in low_chg:
            msg += ", and it is charging"
        elif pct >= 95 and ("high" in low_chg or "full" in low_chg):
            msg += ", and it looks fully charged"
    else:
        msg += ", and you are running on battery power"
        if "low" in charge.lower() or "critical" in charge.lower():
            msg += ", and the charge is low"

    return True, msg + "."


def hotspot_toggle() -> tuple[bool, str]:
    script = "netsh wlan show hostednetwork 2>&1 | Out-String"
    code, out, _err = _run_ps(script, timeout=15)
    blob = (out or "").lower()
    if "started" in blob or "active" in blob:
        return hotspot_set(False)
    return hotspot_set(True)


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
        act = str(intent.get("action", "toggle")).strip().lower()
        if act == "toggle":
            return hotspot_toggle()
        ok_on = act == "on"
        return hotspot_set(ok_on)
    if itype == "battery_status":
        return get_battery_status()
    if itype == "volume_status":
        return get_volume_status()
    return False, "Unknown system action."
