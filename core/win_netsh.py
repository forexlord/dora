"""Wi-Fi control via netsh (no PowerShell)."""

from __future__ import annotations

import re

from core.win_subprocess import run_no_console

_WIFI_NAME_HINTS = ("wi-fi", "wifi", "wireless", "wlan")


def _find_wifi_interface() -> str | None:
    result = run_no_console(
        ["netsh", "interface", "show", "interface"],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if result.returncode != 0:
        return None
    for line in (result.stdout or "").splitlines():
        parts = [p.strip() for p in line.split()]
        if len(parts) < 4:
            continue
        name = parts[-1]
        if any(h in name.lower() for h in _WIFI_NAME_HINTS):
            return name
    match = re.search(r"(Wi-?Fi|Wireless)", result.stdout or "", re.IGNORECASE)
    if match:
        return match.group(0)
    return None


def wifi_set_netsh(enabled: bool) -> tuple[bool, str]:
    iface = _find_wifi_interface()
    if not iface:
        return False, "No Wi-Fi adapter found."
    state = "enabled" if enabled else "disabled"
    result = run_no_console(
        ["netsh", "interface", "set", "interface", f"name={iface}", f"admin={state}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    if result.returncode == 0:
        return True, "Wi-Fi turned on." if enabled else "Wi-Fi turned off."
    err = (result.stderr or result.stdout or "").strip()
    return False, err or f"Could not set Wi-Fi to {state} (try running as administrator)."


def wifi_toggle_netsh() -> tuple[bool, str]:
    iface = _find_wifi_interface()
    if not iface:
        return False, "No Wi-Fi adapter found."
    show = run_no_console(
        ["netsh", "interface", "show", "interface", f"name={iface}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    blob = (show.stdout or "").lower()
    currently_connected = "connected" in blob and "disconnected" not in blob.split("state")[-1][:20]
    return wifi_set_netsh(not currently_connected)
