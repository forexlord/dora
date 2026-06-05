"""Working directory and JSON config I/O."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return json.loads(file_path.read_text(encoding="utf-8"))


def resolve_working_directory() -> Path:
    """
    Where config.json, models/, permissions, and the optional ``apps/`` folder live.

    Set DORA_HOME to that folder (recommended after pip install).
    VOICE_ASSISTANT_HOME is still accepted if DORA_HOME is unset.
    If both unset, the current working directory is used.
    """
    raw = (
        os.environ.get("DORA_HOME", "").strip()
        or os.environ.get("VOICE_ASSISTANT_HOME", "").strip()
    )
    if raw:
        root = Path(raw).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root
    return Path.cwd().resolve()
