"""Structured logging for Dora (mirrors to dora.log in background mode)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def log_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Dora"


def setup_logging(*, background: bool = False) -> logging.Logger:
    """
    Configure the ``dora`` logger once per process.
    Foreground runs still log to file; Rich handles the interactive console.
    """
    logger = logging.getLogger("dora")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    base = log_dir()
    base.mkdir(parents=True, exist_ok=True)
    log_path = base / "dora.log"

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(file_handler)

    if not background and getattr(sys.stderr, "isatty", lambda: False)():
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setLevel(logging.WARNING)
        stream_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(stream_handler)

    logger.propagate = False
    return logger
