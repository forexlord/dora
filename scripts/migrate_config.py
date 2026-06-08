"""One-shot config migration for the installed Dora copy."""

from __future__ import annotations

import sys
from pathlib import Path

from core.config import load_dora_config
from core.paths import resolve_working_directory


def main() -> int:
    root = resolve_working_directory()
    cfg_path = root / "config.json"
    if not cfg_path.is_file():
        print(f"Missing {cfg_path}", file=sys.stderr)
        return 1
    cfg = load_dora_config(cfg_path, persist_migrations=True)
    print(f"Migrated {cfg_path}")
    print(f"  stt_engine={cfg.stt_engine!r}")
    print(f"  whisper_model={cfg.whisper_model!r}")
    print(f"  config_schema_version={cfg.config_schema_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
