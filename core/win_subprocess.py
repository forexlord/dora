"""Run subprocesses on Windows without flashing a visible PowerShell/CMD window."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_Arg = str | bytes | Path
Cmd = Sequence[_Arg] | str


def _creationflags_no_window() -> int:
    if sys.platform != "win32":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _kwargs_with_hidden(kwargs: dict[str, Any]) -> dict[str, Any]:
    out = dict(kwargs)
    cf = _creationflags_no_window()
    if cf:
        out["creationflags"] = int(out.get("creationflags", 0)) | cf
    return out


def run_no_console(cmd: Cmd, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    """Like subprocess.run, but hides the console on Windows when supported."""
    return subprocess.run(cmd, **_kwargs_with_hidden(kwargs))  # type: ignore[arg-type]


def popen_no_console(cmd: Cmd, **kwargs: Any) -> subprocess.Popen[Any]:
    """Like subprocess.Popen, but hides the console on Windows when supported."""
    return subprocess.Popen(cmd, **_kwargs_with_hidden(kwargs))  # type: ignore[arg-type]
