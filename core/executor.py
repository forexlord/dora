from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

from core.app_close import (
    build_process_patterns,
    build_window_title_needles,
    close_by_window_titles,
    close_uwp_by_name,
    kill_by_process_patterns,
)
from core.app_resolve import apply_app_alias, resolve_app_key
from core.discovery import build_runtime_launch_index, find_app_executable, normalize_app_name
from core.permissions import PermissionStore
from core.session import heard_is_confirmation
from core.win_subprocess import popen_no_console, run_no_console


class CommandExecutor:
    """Runs OS actions. Open/close resolve app names from a live index (Start Menu, UWP, ``apps/``)."""

    _LAUNCH_INDEX_CACHE_TTL_SEC = 45.0

    def __init__(
        self,
        permission_store: PermissionStore,
        *,
        apps_dir: str | Path = "apps",
        auto_discover_apps: bool = True,
        trust_mapped_apps: bool = False,
    ) -> None:
        self.permission_store = permission_store
        self.apps_dir = Path(apps_dir)
        self.auto_discover_apps = auto_discover_apps
        self.trust_mapped_apps = trust_mapped_apps
        self._launch_cache: tuple[dict[str, str], float, float] | None = None

    def _confirm(self, prompt: str, confirm_fn: Callable[[str], bool] | None = None) -> bool:
        if confirm_fn is not None:
            return bool(confirm_fn(prompt))
        answer = input(f"{prompt} (yes/no): ").strip().lower()
        return heard_is_confirmation(answer)

    @staticmethod
    def _pretty_app_label(key: str) -> str:
        """Short spoken-style label (codex → Codex, visual studio code → Visual Studio Code)."""
        parts = key.strip().split()
        if not parts:
            return key
        out: list[str] = []
        for p in parts:
            if not p:
                continue
            out.append(p[:1].upper() + p[1:].lower() if len(p) > 1 else p.upper())
        return " ".join(out)

    def _disambiguation_prompt(
        self,
        *,
        suggested_key: str,
        heard_display: str,
        heard_key: str,
        for_open: bool,
    ) -> str:
        label = self._pretty_app_label(suggested_key)
        heard = (heard_display or heard_key).strip() or heard_key
        return f'Did you mean {label}? You said: "{heard}".'

    def _resolve_app_key(self, app_key: str, candidates: dict[str, str]) -> tuple[str | None, float]:
        return resolve_app_key(app_key, candidates)

    def _apps_dir_mtime(self) -> float:
        if not self.apps_dir.is_dir():
            return 0.0
        latest = self.apps_dir.stat().st_mtime
        try:
            for p in self.apps_dir.iterdir():
                if p.is_file():
                    latest = max(latest, p.stat().st_mtime)
        except OSError:
            pass
        return latest

    def _get_launch_index(self) -> dict[str, str]:
        now = time.monotonic()
        apps_mtime = self._apps_dir_mtime()
        if self._launch_cache is not None:
            cached_index, cached_at, cached_apps_mtime = self._launch_cache
            if (
                now - cached_at < self._LAUNCH_INDEX_CACHE_TTL_SEC
                and apps_mtime == cached_apps_mtime
            ):
                return cached_index
        index, _stats = build_runtime_launch_index(self.apps_dir)
        self._launch_cache = (index, now, apps_mtime)
        return index

    def _scan_permission_allowed(self, confirm_fn: Callable[[str], bool] | None = None) -> bool:
        scan_key = "__scan_apps__"
        if self.permission_store.is_allowed(scan_key):
            return True
        allowed = self._confirm(
            "Allow one-time access to scan common app folders for auto-discovery?",
            confirm_fn,
        )
        self.permission_store.set_allowed(scan_key, allowed)
        return allowed

    def _not_found_message(self, app_name: str, app_key: str) -> str:
        label = app_name.strip() or app_key
        return f'Could not find "{label}".'

    def _target_exists(self, target: str) -> bool:
        if target.startswith("uwp:"):
            return True
        return Path(target).exists()

    def _launch_target(self, target: str) -> None:
        if target.startswith("uwp:"):
            app_id = target.split(":", 1)[1]
            popen_no_console(["explorer.exe", f"shell:AppsFolder\\{app_id}"], shell=False)
            return
        if target.lower().endswith(".lnk"):
            os.startfile(target)  # type: ignore[attr-defined]
            return
        popen_no_console([target], shell=False)

    def _close_file_explorer_windows(self) -> bool:
        ps_cmd = (
            "$shell = New-Object -ComObject Shell.Application; "
            "$wins = @($shell.Windows() | Where-Object { "
            "$_.FullName -and $_.FullName -like '*explorer.exe' }); "
            "if ($wins.Count -gt 0) { $wins | ForEach-Object { $_.Quit() }; exit 0 } else { exit 1 }"
        )
        result = run_no_console(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def _resolve_launch_key(
        self, app_key: str, index: dict[str, str]
    ) -> tuple[str, str | None, float]:
        alias_key = apply_app_alias(app_key)
        if alias_key in index:
            return alias_key, alias_key, 1.0
        if app_key in index:
            return app_key, app_key, 1.0
        resolved_key, confidence = self._resolve_app_key(alias_key, index)
        if resolved_key is None and alias_key != app_key:
            resolved_key, confidence = self._resolve_app_key(app_key, index)
        if resolved_key and confidence >= 0.58:
            return resolved_key, resolved_key, confidence
        return app_key, resolved_key, confidence if resolved_key else 0.0

    def open_app(
        self, app_name: str, confirm_fn: Callable[[str], bool] | None = None
    ) -> tuple[bool, str]:
        display_label = app_name.strip()
        app_key = normalize_app_name(app_name)
        if not app_key:
            return False, self._not_found_message(app_name, app_key)

        index = self._get_launch_index()
        heard_key = app_key
        app_key, resolved_key, confidence = self._resolve_launch_key(app_key, index)
        compare_key = apply_app_alias(heard_key)
        if (
            resolved_key
            and resolved_key != heard_key
            and resolved_key != compare_key
            and confidence < 0.80
        ):
            if not self._confirm(
                self._disambiguation_prompt(
                    suggested_key=resolved_key,
                    heard_display=display_label,
                    heard_key=heard_key,
                    for_open=True,
                ),
                confirm_fn,
            ):
                return (
                    False,
                    f"Canceled — not opening {self._pretty_app_label(resolved_key)}.",
                )

        app_path = index.get(app_key)
        if not app_path:
            if self.auto_discover_apps:
                if not self._scan_permission_allowed(confirm_fn):
                    return (
                        False,
                        f"{self._not_found_message(app_name, app_key)} "
                        "Deep scan permission was denied.",
                    )
                discovered = find_app_executable(app_key)
                if discovered:
                    app_path = discovered
                else:
                    return False, self._not_found_message(app_name, app_key)
            else:
                return False, self._not_found_message(app_name, app_key)

        if not self._target_exists(app_path):
            return (
                False,
                f'{self._not_found_message(app_name, app_key)} '
                f"(expected path is missing: {app_path})",
            )

        if self.trust_mapped_apps:
            self.permission_store.set_allowed(app_key, True)

        if not self.permission_store.is_allowed(app_key):
            if not self._confirm(
                f"Allow {self._pretty_app_label(app_key)}?", confirm_fn
            ):
                self.permission_store.set_allowed(app_key, False)
                return False, f"Permission denied for {app_key}"
            self.permission_store.set_allowed(app_key, True)

        self._launch_target(app_path)
        opened_as = display_label or app_key
        return True, f"Okay, I opened {opened_as}."

    def close_app(
        self,
        app_name: str,
        *,
        force: bool = False,
        confirm_fn: Callable[[str], bool] | None = None,
    ) -> tuple[bool, str]:
        display_label = app_name.strip()
        app_key = normalize_app_name(app_name)
        index = self._get_launch_index()
        heard_key = app_key
        app_key, resolved_key, confidence = self._resolve_launch_key(app_key, index)
        compare_key = apply_app_alias(heard_key)
        if (
            resolved_key
            and resolved_key != heard_key
            and resolved_key != compare_key
            and confidence < 0.80
        ):
            if not self._confirm(
                self._disambiguation_prompt(
                    suggested_key=resolved_key,
                    heard_display=display_label,
                    heard_key=heard_key,
                    for_open=False,
                ),
                confirm_fn,
            ):
                return (
                    False,
                    f"Canceled — not closing {self._pretty_app_label(resolved_key)}.",
                )

        if force:
            if not self._confirm(f"Force close {app_key}?", confirm_fn):
                return False, f"Close canceled for {app_key}"

        target = index.get(app_key, "")
        pretty = self._pretty_app_label(app_key)
        if app_key in {"file explorer", "explorer", "windows explorer"}:
            if self._close_file_explorer_windows():
                return True, "Okay, I closed File Explorer."

        if target.startswith("uwp:"):
            if close_uwp_by_name(app_key, force=force):
                return True, f"Okay, I closed {pretty}."
            needles = build_window_title_needles(app_key, pretty)
            if close_by_window_titles(needles, force=force):
                return True, f"Okay, I closed {pretty}."

        patterns = build_process_patterns(app_key, target)
        if kill_by_process_patterns(patterns, force=force):
            return True, f"Okay, I closed {pretty}."

        needles = build_window_title_needles(app_key, pretty)
        if close_by_window_titles(needles, force=force):
            return True, f"Okay, I closed {pretty}."

        hint = (
            f" Say force close {app_key} if you need to end it."
            if not force
            else ""
        )
        return False, f"I couldn't find a running process for {pretty}.{hint}"

    def shutdown(
        self,
        require_confirmation: bool = True,
        confirm_fn: Callable[[str], bool] | None = None,
    ) -> tuple[bool, str]:
        if require_confirmation:
            if not self._confirm("Confirm shutdown?", confirm_fn):
                return False, "Shutdown canceled"

        run_no_console(["shutdown", "/s", "/t", "5"], shell=False, check=False)
        return True, "Shutdown command sent"
