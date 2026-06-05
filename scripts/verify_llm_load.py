"""Exit 0 if bundled llama-server can load the configured GGUF; else exit 1."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    os.chdir(root)

    cfg_path = root / "config.json"
    if not cfg_path.is_file():
        print(f"Missing {cfg_path}", file=sys.stderr)
        return 1

    config = json.loads(cfg_path.read_text(encoding="utf-8"))
    from core.bootstrap import ensure_llama_tools, ensure_llm_model, llm_model_path_from_config
    from core.llama_server import probe_server_load, stop_llama_server

    ok_t, msg_t = ensure_llama_tools(config)
    if not ok_t:
        print(msg_t, file=sys.stderr)
        return 1

    ok_m, msg_m = ensure_llm_model(config)
    if not ok_m:
        print(msg_m, file=sys.stderr)
        return 1

    model_path = llm_model_path_from_config(config)
    print("Starting llama-server and loading model (first time may take several minutes)...", flush=True)
    try:
        ok, msg = probe_server_load(config, model_path)
    finally:
        stop_llama_server()

    if ok:
        print(msg)
        return 0
    print(msg, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
