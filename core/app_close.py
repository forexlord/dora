"""Find and close running Windows apps (including browser PWAs and shortcuts)."""

from __future__ import annotations

from pathlib import Path

from core.win_subprocess import run_no_console


def resolve_shortcut_target(lnk_path: str) -> str | None:
    """Return the TargetPath of a Windows .lnk shortcut, if readable."""
    path = lnk_path.strip()
    if not path.lower().endswith(".lnk"):
        return None
    safe = path.replace("'", "''")
    ps_cmd = (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{safe}'); "
        "Write-Output $s.TargetPath"
    )
    result = run_no_console(
        ["powershell", "-NoProfile", "-Command", ps_cmd],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if result.returncode != 0:
        return None
    target = (result.stdout or "").strip()
    return target or None


def build_process_patterns(app_key: str, target: str) -> list[str]:
    """Executable / process-name patterns to try with taskkill or Get-Process."""
    seen: set[str] = set()
    patterns: list[str] = []

    def add(raw: str) -> None:
        token = raw.strip().replace('"', "")
        if not token:
            return
        key = token.lower()
        if key in seen:
            return
        seen.add(key)
        patterns.append(token)

    add(app_key.replace(" ", ""))
    add(app_key)
    if not target:
        return patterns

    if target.startswith("uwp:"):
        add(app_key)
        return patterns

    path = Path(target)
    if path.suffix.lower() == ".lnk":
        resolved = resolve_shortcut_target(str(path))
        if resolved:
            path = Path(resolved)
    if path.suffix.lower() in {".exe", ".lnk"}:
        add(path.stem)
    elif path.suffix.lower() in {".bat", ".cmd"}:
        add(path.stem)

    return patterns


def build_window_title_needles(app_key: str, pretty_label: str) -> list[str]:
    """Phrases to match against MainWindowTitle (longest first)."""
    seen: set[str] = set()
    needles: list[str] = []

    def add(text: str) -> None:
        cleaned = " ".join(text.split()).strip()
        if len(cleaned) < 3:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        needles.append(cleaned)

    add(pretty_label)
    add(app_key)
    parts = app_key.split()
    if len(parts) >= 2:
        add(" ".join(parts))
    return sorted(needles, key=len, reverse=True)


def kill_by_process_patterns(patterns: list[str], *, force: bool) -> bool:
    for raw in patterns:
        proc = raw.strip().replace('"', "")
        if not proc:
            continue
        exe_name = proc if proc.lower().endswith(".exe") else f"{proc}.exe"
        args = ["taskkill", "/IM", exe_name, "/T"]
        if force:
            args.insert(1, "/F")
        result = run_no_console(
            args,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return True

    for raw in patterns:
        pattern = raw.replace(" ", "*")
        stop = "Stop-Process -Force" if force else "Stop-Process"
        ps_cmd = (
            "$procs = Get-Process | Where-Object { $_.ProcessName -like "
            f"'*{pattern}*' }}; "
            f"if ($procs) {{ $procs | {stop}; exit 0 }} else {{ exit 1 }}"
        )
        result = run_no_console(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return True
    return False


def close_by_window_titles(needles: list[str], *, force: bool) -> bool:
    """
    Close apps whose main window title contains a known app name.

    Works for Chrome/Edge PWAs (Google Meet, Teams, etc.) where the process is
    chrome.exe/msedge.exe but the window title includes the app name.
    """
    if not needles:
        return False
    escaped = [n.replace("'", "''") for n in needles if n.strip()]
    if not escaped:
        return False
    array = ", ".join(f"'{n}'" for n in escaped)
    if force:
        body = (
            f"$needles = @({array}); "
            "$closed = $false; "
            "Get-Process | Where-Object { "
            "$_.MainWindowHandle -ne 0 -and $_.MainWindowTitle } | ForEach-Object { "
            "$proc = $_; "
            "foreach ($n in $needles) { "
            "if ($proc.MainWindowTitle -like (\"*\" + $n + \"*\")) { "
            "$proc | Stop-Process -Force; $closed = $true; break "
            "} } }; "
            "if ($closed) { exit 0 } else { exit 1 }"
        )
    else:
        body = (
            f"$needles = @({array}); "
            "$closed = $false; "
            "Get-Process | Where-Object { "
            "$_.MainWindowHandle -ne 0 -and $_.MainWindowTitle } | ForEach-Object { "
            "$proc = $_; "
            "foreach ($n in $needles) { "
            "if ($proc.MainWindowTitle -like (\"*\" + $n + \"*\")) { "
            "[void]$proc.CloseMainWindow(); $closed = $true; break "
            "} } }; "
            "if ($closed) { Start-Sleep -Milliseconds 400; exit 0 } else { exit 1 }"
        )
    result = run_no_console(
        ["powershell", "-NoProfile", "-Command", body],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    return result.returncode == 0


def close_uwp_by_name(app_key: str, *, force: bool) -> bool:
    """Try to stop a visible UWP window by matching its title to the app name."""
    needles = build_window_title_needles(app_key, app_key)
    return close_by_window_titles(needles, force=force)
