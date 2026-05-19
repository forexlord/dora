"""Console entry point for setuptools / pip (`dora` and `dora-background` commands)."""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path


def _log_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Dora"


class _Tee:
    """Write to console and to dora.log (Rich still sees a TTY on the first stream)."""

    __slots__ = ("_streams",)

    def __init__(self, *streams: object) -> None:
        self._streams = streams

    def write(self, data: str) -> int:
        for s in self._streams:
            try:
                s.write(data)  # type: ignore[attr-defined]
            except Exception:
                pass
        for s in self._streams:
            try:
                s.flush()  # type: ignore[attr-defined]
            except Exception:
                pass
        return len(data)

    def flush(self) -> None:
        for s in self._streams:
            try:
                s.flush()  # type: ignore[attr-defined]
            except Exception:
                pass

    def isatty(self) -> bool:
        f = self._streams[0]
        return bool(getattr(f, "isatty", lambda: False)())

    def fileno(self) -> int:
        f = self._streams[0]
        if hasattr(f, "fileno"):
            return f.fileno()  # type: ignore[no-any-return]
        raise OSError("stream has no fileno")


def _configure_background_stdio() -> None:
    """No console (pythonw): send stdout/stderr to %LOCALAPPDATA%\\Dora\\dora.log."""
    if os.environ.get("DORA_BACKGROUND") != "1":
        return
    base = _log_dir()
    base.mkdir(parents=True, exist_ok=True)
    log_path = base / "dora.log"
    handle = open(log_path, "a", encoding="utf-8", buffering=1)
    handle.write(f"\n--- Dora start {datetime.datetime.now().isoformat()} (background) ---\n")
    handle.flush()
    sys.stdout = sys.stderr = handle


def _configure_foreground_log() -> None:
    """Normal terminal run: mirror output to %LOCALAPPDATA%\\Dora\\dora.log."""
    base = _log_dir()
    base.mkdir(parents=True, exist_ok=True)
    log_path = base / "dora.log"
    logf = open(log_path, "a", encoding="utf-8", buffering=1)
    logf.write(f"\n--- Dora session {datetime.datetime.now().isoformat()} (terminal) ---\n")
    logf.flush()

    out, err = sys.stdout, sys.stderr
    if out is not None and getattr(out, "isatty", lambda: False)():
        sys.stdout = _Tee(out, logf)
        sys.stderr = _Tee(err if err is not None else out, logf)
    else:
        logf.close()


def _cli_install_startup() -> None:
    from core.windows_startup import install_user_startup

    args = list(sys.argv[1:])
    home: Path | None = None
    if "--install-startup" in args:
        i = args.index("--install-startup")
        if i + 1 < len(args) and not args[i + 1].startswith("-"):
            home = Path(args[i + 1]).expanduser()
    ok, msg = install_user_startup(home)
    print(msg)
    raise SystemExit(0 if ok else 1)


def _cli_uninstall_startup() -> None:
    from core.windows_startup import uninstall_user_startup

    ok, msg = uninstall_user_startup()
    print(msg)
    raise SystemExit(0 if ok else 1)


def main() -> None:
    if "--install-startup" in sys.argv:
        _cli_install_startup()
    if "--uninstall-startup" in sys.argv:
        _cli_uninstall_startup()

    _configure_background_stdio()
    if os.environ.get("DORA_BACKGROUND") != "1":
        _configure_foreground_log()

    from core.application import run_assistant

    run_assistant()


def main_background() -> None:
    """Entry point for `dora-background` / hidden startup (sets DORA_BACKGROUND)."""
    os.environ.setdefault("DORA_BACKGROUND", "1")
    main()


if __name__ == "__main__":
    main()
