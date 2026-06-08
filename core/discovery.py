from __future__ import annotations

import json
import os
from pathlib import Path

from core.app_resolve import well_known_windows_apps
from core.win_subprocess import run_no_console


def normalize_app_name(name: str) -> str:
    cleaned = name.strip().lower().replace("_", " ").replace("-", " ")
    return " ".join(cleaned.split())


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    for env_key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "APPDATA"):
        value = os.environ.get(env_key)
        if value:
            root = Path(value)
            if root.exists():
                roots.append(root)
    return roots


def _start_menu_dirs() -> list[Path]:
    dirs: list[Path] = []
    app_data = os.environ.get("APPDATA")
    program_data = os.environ.get("ProgramData")
    if app_data:
        dirs.append(Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    if program_data:
        dirs.append(Path(program_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return [d for d in dirs if d.exists()]


def discover_start_menu_shortcuts() -> dict[str, str]:
    discovered: dict[str, str] = {}
    for menu_dir in _start_menu_dirs():
        try:
            for lnk in menu_dir.rglob("*.lnk"):
                key = normalize_app_name(lnk.stem)
                if key and key not in discovered:
                    discovered[key] = str(lnk)
        except (PermissionError, OSError):
            continue
    return discovered


def discover_uwp_start_apps() -> dict[str, str]:
    discovered: dict[str, str] = {}
    command = (
        "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Depth 3 -Compress"
    )
    try:
        result = run_no_console(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except Exception:
        return discovered

    if result.returncode != 0 or not result.stdout.strip():
        return discovered

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return discovered

    entries = payload if isinstance(payload, list) else [payload]
    for item in entries:
        if not isinstance(item, dict):
            continue
        name = item.get("Name")
        app_id = item.get("AppID")
        if not name or not app_id:
            continue
        key = normalize_app_name(str(name))
        if key and key not in discovered:
            discovered[key] = f"uwp:{app_id}"
    return discovered


def build_app_index() -> tuple[dict[str, str], dict[str, int]]:
    """
    Fast full index from Start Menu shortcuts + UWP start apps.
    """
    combined: dict[str, str] = {}
    shortcuts = discover_start_menu_shortcuts()
    uwp_apps = discover_uwp_start_apps()
    combined.update(well_known_windows_apps())
    combined.update(shortcuts)
    combined.update(uwp_apps)
    stats = {
        "start_menu_shortcuts": len(shortcuts),
        "uwp_start_apps": len(uwp_apps),
        "total_indexed": len(combined),
    }
    return combined, stats


def discover_apps_dir(apps_dir: Path) -> dict[str, str]:
    """
    Map normalized display names to absolute paths for launchables dropped in ``apps_dir``.

    Only non-hidden files directly in that folder are considered (no subfolders),
    so names match what users see next to ``config.json``.
    """
    discovered: dict[str, str] = {}
    if not apps_dir.is_dir():
        return discovered
    allowed = {".exe", ".lnk", ".bat", ".cmd"}
    for entry in sorted(apps_dir.iterdir()):
        if not entry.is_file() or entry.name.startswith("."):
            continue
        if entry.suffix.lower() not in allowed:
            continue
        key = normalize_app_name(entry.stem)
        if not key:
            continue
        discovered[key] = str(entry.resolve())
    return discovered


def build_runtime_launch_index(apps_dir: Path | None) -> tuple[dict[str, str], dict[str, int]]:
    """
    Start Menu + UWP entries, then entries from ``apps_dir`` (local shortcuts win on name clash).
    """
    system, stats = build_app_index()
    merged = dict(system)
    if apps_dir is not None:
        local = discover_apps_dir(apps_dir)
        merged.update(local)
        stats = {
            **stats,
            "apps_folder": len(local),
            "total_indexed": len(merged),
        }
    return merged, stats


def find_app_executable(app_name: str, max_results: int = 20) -> str | None:
    """
    Best-effort app discovery for Windows executables.
    Scans common install roots and returns the best matching .exe path.
    """
    query = normalize_app_name(app_name)
    if not query:
        return None

    matched_paths: list[Path] = []
    query_exe = f"{query}.exe"

    for root in _candidate_roots():
        try:
            for exe_path in root.rglob("*.exe"):
                name = exe_path.name.lower()
                stem = exe_path.stem.lower()
                if name == query_exe or query in stem or query in name:
                    matched_paths.append(exe_path)
                    if len(matched_paths) >= max_results:
                        break
        except (PermissionError, OSError):
            # Skip inaccessible folders.
            continue
        if len(matched_paths) >= max_results:
            break

    if not matched_paths:
        return None

    def score(path: Path) -> tuple[int, int]:
        stem = path.stem.lower()
        exact = 1 if stem == query else 0
        # Prefer shorter paths if multiple are similar.
        return (exact, -len(str(path)))

    best = sorted(matched_paths, key=score, reverse=True)[0]
    return str(best)
