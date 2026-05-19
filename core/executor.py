from __future__ import annotations

import difflib
import os
import time
from pathlib import Path
from typing import Callable

from core.discovery import build_runtime_launch_index, find_app_executable, normalize_app_name
from core.permissions import PermissionStore
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
        trust_mapped_apps: bool = True,
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
        return answer in {"yes", "y", "confirm"}

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
        verb = "open" if for_open else "close"
        return (
            f"Did you mean {label}? You said: \"{heard}\". "
            f'Say yes or confirm to {verb} {label}.'
        )

    def _resolve_app_key(self, app_key: str, candidates: dict[str, str]) -> tuple[str | None, float]:
        if app_key in candidates:
            return app_key, 1.0
        if not candidates:
            return None, 0.0

        def compact(text: str) -> str:
            return "".join(ch for ch in text.lower() if ch.isalnum())

        def consonant_key(text: str) -> str:
            source = compact(text)
            if not source:
                return ""
            vowels = set("aeiou")
            out: list[str] = []
            prev = ""
            for ch in source:
                if ch in vowels:
                    continue
                if ch != prev:
                    out.append(ch)
                    prev = ch
            return "".join(out)

        query_tokens = set(app_key.split())
        query_compact = compact(app_key)
        query_cons = consonant_key(app_key)
        best_key = None
        best_score = 0.0
        for candidate in candidates:
            cand_tokens = set(candidate.split())
            overlap = len(query_tokens & cand_tokens)
            token_score = overlap / max(len(query_tokens), len(cand_tokens), 1)
            ratio = difflib.SequenceMatcher(None, app_key, candidate).ratio()
            compact_ratio = difflib.SequenceMatcher(
                None, query_compact, compact(candidate)
            ).ratio()
            cons_ratio = difflib.SequenceMatcher(
                None, query_cons, consonant_key(candidate)
            ).ratio()
            score = (
                (0.35 * ratio)
                + (0.15 * token_score)
                + (0.35 * compact_ratio)
                + (0.15 * cons_ratio)
            )
            if score > best_score:
                best_key = candidate
                best_score = score

        close = difflib.get_close_matches(app_key, list(candidates.keys()), n=1, cutoff=0.55)
        if close:
            close_ratio = difflib.SequenceMatcher(None, app_key, close[0]).ratio()
            if close_ratio > best_score:
                best_key = close[0]
                best_score = close_ratio

        if best_key is None:
            return None, 0.0
        return best_key, best_score

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

    def open_app(
        self, app_name: str, confirm_fn: Callable[[str], bool] | None = None
    ) -> tuple[bool, str]:
        display_label = app_name.strip()
        app_key = normalize_app_name(app_name)
        if not app_key:
            return False, self._not_found_message(app_name, app_key)

        index = self._get_launch_index()
        resolved_key, confidence = self._resolve_app_key(app_key, index)
        if resolved_key and resolved_key != app_key and confidence >= 0.42:
            if confidence < 0.85:
                if not self._confirm(
                    self._disambiguation_prompt(
                        suggested_key=resolved_key,
                        heard_display=display_label,
                        heard_key=app_key,
                        for_open=True,
                    ),
                    confirm_fn,
                ):
                    return (
                        False,
                        f"Canceled — not opening {self._pretty_app_label(resolved_key)}. "
                        f'You said: "{display_label or app_key}".',
                    )
            app_key = resolved_key

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
            if not self._confirm(f"Allow access to {app_key}?", confirm_fn):
                self.permission_store.set_allowed(app_key, False)
                return False, f"Permission denied for {app_key}"
            self.permission_store.set_allowed(app_key, True)

        self._launch_target(app_path)
        opened_as = display_label or app_key
        return True, f"Opened {opened_as}"

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
        resolved_key, confidence = self._resolve_app_key(app_key, index)
        if resolved_key and resolved_key != app_key and confidence >= 0.42:
            if confidence < 0.85:
                if not self._confirm(
                    self._disambiguation_prompt(
                        suggested_key=resolved_key,
                        heard_display=display_label,
                        heard_key=app_key,
                        for_open=False,
                    ),
                    confirm_fn,
                ):
                    return (
                        False,
                        f"Canceled — not closing {self._pretty_app_label(resolved_key)}. "
                        f'You said: "{display_label or app_key}".',
                    )
            app_key = resolved_key

        if force:
            if not self._confirm(f"Force close {app_key}?", confirm_fn):
                return False, f"Close canceled for {app_key}"

        target = index.get(app_key, "")
        if app_key in {"file explorer", "explorer", "windows explorer"}:
            if self._close_file_explorer_windows():
                return True, "Closed file explorer windows"

        patterns: list[str] = [app_key.replace(" ", "")]
        if target.startswith("uwp:"):
            patterns.append(app_key)
        elif target:
            path = Path(target)
            if path.suffix.lower() in {".exe", ".lnk"}:
                patterns.append(path.stem)

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
                return True, f"Closed {app_key}"

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
                return True, f"Closed {app_key}"

        hint = (
            f" Say force close {app_key} if you need to end it."
            if not force
            else ""
        )
        return False, f"I couldn't find a running process for {app_key}.{hint}"

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
