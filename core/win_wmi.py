"""WMI monitor brightness via comtypes (no PowerShell)."""

from __future__ import annotations

import logging
import sys
from typing import Any

logger = logging.getLogger("dora.wmi")

_UNAVAILABLE = (
    "Screen brightness is not available on this display "
    "(common on external monitors and desktops)."
)


def _wmi_root(namespace: str = r"root\wmi") -> Any | None:
    if sys.platform != "win32":
        return None
    try:
        import comtypes.client

        return comtypes.client.GetObject(f"winmgmts:\\\\.\\{namespace}")
    except Exception:
        logger.exception("WMI connect failed for %s", namespace)
        return None


def get_brightness_percent_wmi() -> tuple[bool, int | None, str]:
    wmi = _wmi_root()
    if wmi is None:
        return False, None, _UNAVAILABLE
    try:
        monitors = wmi.InstancesOf("WmiMonitorBrightness")
        for monitor in monitors:
            value = int(getattr(monitor, "CurrentBrightness", -1))
            if 0 <= value <= 100:
                return True, value, ""
    except Exception:
        logger.exception("WMI read brightness failed")
    return False, None, _UNAVAILABLE


def set_brightness_percent_wmi(percent: int) -> tuple[bool, str]:
    level = max(0, min(100, int(percent)))
    wmi = _wmi_root()
    if wmi is None:
        return False, _UNAVAILABLE
    try:
        methods = wmi.InstancesOf("WmiMonitorBrightnessMethods")
        for method in methods:
            method.WmiSetBrightness(1, level)
            return True, f"Brightness set to about {level} percent."
    except Exception:
        logger.exception("WMI set brightness failed")
    return False, _UNAVAILABLE
