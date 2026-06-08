"""Platform guards for Windows-only features."""

from __future__ import annotations

import sys


def require_windows(feature: str = "Dora") -> None:
    if sys.platform == "win32":
        return
    raise SystemExit(
        f"{feature} runs on Windows 10/11 only. "
        f"Detected platform: {sys.platform!r}."
    )
