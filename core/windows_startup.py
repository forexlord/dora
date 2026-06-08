"""Windows: add/remove Dora in the current user's Startup folder (sign-in launch)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from core.win_subprocess import run_no_console


def _startup_folder() -> Path:
    return (
        Path(os.environ.get("APPDATA", ""))
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )


def _bundle_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Dora"


def _pythonw() -> Path:
    exe = Path(sys.executable)
    cand = exe.parent / "pythonw.exe"
    return cand if cand.is_file() else exe


def _background_launcher(dora_home: Path) -> tuple[Path, str]:
    """Installed venv entry point, else pythonw -m core.cli (dev)."""
    bg = dora_home / "venv" / "Scripts" / "dora-background.exe"
    if bg.is_file():
        return bg, ""
    pyw = _pythonw()
    return pyw, " -m core.cli"


def _ps_single_quoted(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def install_user_startup(dora_home: Path | None = None) -> tuple[bool, str]:
    """
    Create %LOCALAPPDATA%\\Dora\\DoraStart.vbs and a Startup shortcut (hidden window).
    dora_home: folder with config.json (default: cwd).
    """
    if sys.platform != "win32":
        return False, "Automatic startup is only supported on Windows."

    home = (dora_home or Path.cwd()).resolve()
    cfg = home / "config.json"
    if not cfg.is_file():
        return (
            False,
            f"No config.json in:\n  {home}\n"
            "Open a terminal in your Dora project folder and run:\n"
            "  dora --install-startup",
        )

    bundle = _bundle_dir()
    bundle.mkdir(parents=True, exist_ok=True)
    launcher, launcher_args = _background_launcher(home)
    dh = str(home).replace('"', '""')
    lp = str(launcher).replace('"', '""')
    vbs = bundle / "DoraStart.vbs"
    vbs.write_text(
        "Set sh = CreateObject(\"WScript.Shell\")\n"
        f"sh.Environment(\"Process\")(\"DORA_HOME\") = \"{dh}\"\n"
        'sh.Environment("Process")("DORA_BACKGROUND") = "1"\n'
        f'cmd = Chr(34) & "{lp}" & Chr(34) & "{launcher_args}"\n'
        "sh.Run cmd, 0, False\n",
        encoding="utf-8",
    )

    startup = _startup_folder()
    startup.mkdir(parents=True, exist_ok=True)
    lnk = startup / "Dora.lnk"

    ps1 = bundle / "RegisterStartup.ps1"
    ps1.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        f"$vbs = {_ps_single_quoted(str(vbs))}\n"
        f"$lnk = {_ps_single_quoted(str(lnk))}\n"
        f"$wd = {_ps_single_quoted(str(bundle))}\n"
        "$ws = New-Object -ComObject WScript.Shell\n"
        "$s = $ws.CreateShortcut($lnk)\n"
        "$s.TargetPath = 'wscript.exe'\n"
        "$s.Arguments = '//B \"' + $vbs + '\"'\n"
        "$s.WorkingDirectory = $wd\n"
        "$s.Description = 'Dora voice assistant'\n"
        "$s.Save()\n",
        encoding="utf-8",
    )

    try:
        r = run_no_console(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps1),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except OSError as exc:
        return False, f"Could not run PowerShell: {exc}"
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip() or "unknown error"
        return False, f"Shortcut creation failed: {err}"

    return (
        True,
        "Dora will start in the background when you sign in to Windows.\n"
        f"  Launcher: {launcher}{launcher_args}\n"
        "If something goes wrong, open:\n"
        f"  {bundle / 'dora.log'}\n"
        f"  Launcher script: {vbs}\n"
        f"  Startup shortcut: {lnk}\n"
        f"  Data folder (DORA_HOME): {home}",
    )


def uninstall_user_startup() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Startup removal is only supported on Windows."

    removed: list[str] = []
    lnk = _startup_folder() / "Dora.lnk"
    if lnk.is_file():
        try:
            lnk.unlink()
            removed.append(str(lnk))
        except OSError as exc:
            return False, f"Could not remove {lnk}: {exc}"
    vbs = _bundle_dir() / "DoraStart.vbs"
    if vbs.is_file():
        try:
            vbs.unlink()
            removed.append(str(vbs))
        except OSError as exc:
            return False, f"Could not remove {vbs}: {exc}"
    if not removed:
        return True, "Nothing to remove (no Dora startup entry found)."
    return True, "Removed:\n  " + "\n  ".join(removed)
