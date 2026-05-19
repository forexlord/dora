"""Download Vosk + Ollama model during install (no need to run Dora first)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    os.chdir(root)

    from core.bootstrap import (
        ensure_ollama_model,
        ensure_ollama_runtime,
        ensure_runtime_files,
        ensure_vosk_model,
    )

    print("[Dora setup] Preparing folders…", flush=True)
    ensure_runtime_files()

    cfg_path = root / "config.json"
    if not cfg_path.is_file():
        print(f"[Dora setup] ERROR: Missing {cfg_path}", flush=True)
        return 1

    config = json.loads(cfg_path.read_text(encoding="utf-8"))

    print("[Dora setup] Speech model (Vosk)…", flush=True)
    ok, msg, discovered = ensure_vosk_model(config)
    print(f"  {msg}", flush=True)
    if discovered and discovered != config.get("vosk_model_path"):
        config["vosk_model_path"] = discovered
        cfg_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    print("[Dora setup] Ollama…", flush=True)
    ok_o, msg_o = ensure_ollama_runtime(config)
    print(f"  {msg_o}", flush=True)
    if ok_o:
        ok_m, msg_m = ensure_ollama_model(config)
        print(f"  {msg_m}", flush=True)
    else:
        print(
            "  Install Ollama from https://ollama.com then run this installer again, "
            "or start Dora once Ollama is installed.",
            flush=True,
        )

    print("[Dora setup] Done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
