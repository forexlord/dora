from __future__ import annotations

import json
from pathlib import Path


class PermissionStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    def _load(self) -> dict[str, bool]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict[str, bool]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def is_allowed(self, app_name: str) -> bool:
        data = self._load()
        return bool(data.get(app_name.lower(), False))

    def set_allowed(self, app_name: str, allowed: bool) -> None:
        data = self._load()
        data[app_name.lower()] = bool(allowed)
        self._save(data)
