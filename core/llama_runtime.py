"""Compatibility helpers for LLM setup checks."""

from __future__ import annotations

from pathlib import Path

from core.llama_server import probe_server_load


def gguf_header_valid(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with path.open("rb") as handle:
            return handle.read(4) == b"GGUF"
    except OSError:
        return False


def probe_llama_load(model_path: str, config: dict) -> tuple[bool, str]:
    return probe_server_load(config, model_path)
