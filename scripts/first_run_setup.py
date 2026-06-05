"""Download Vosk, llama.cpp tools, and GGUF during install (no need to run Dora first)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    os.chdir(root)

    from core.bootstrap import (
        ensure_llama_tools,
        ensure_llm_model,
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

    print("[Dora setup] AI tools (llama.cpp for Windows)…", flush=True)
    ok_t, msg_t = ensure_llama_tools(config)
    print(f"  {msg_t}", flush=True)

    print("[Dora setup] Language model (Phi-3 GGUF, ~2.4 GB — may take a while)…", flush=True)
    ok_m, msg_m = ensure_llm_model(config)
    print(f"  {msg_m}", flush=True)

    if ok_t and ok_m:
        print("[Dora setup] Verifying AI can load the model (may take several minutes)…", flush=True)
        verify = subprocess.run(
            [sys.executable, str(root / "scripts" / "verify_llm_load.py")],
            cwd=root,
            check=False,
        )
        if verify.returncode != 0:
            print(
                "  Verification failed. Run Install-Dora.bat again or start Dora and wait for warmup.",
                flush=True,
            )

    print("[Dora setup] Done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
