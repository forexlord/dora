import logging

from core.logging_config import log_dir, setup_logging


def test_log_dir_ends_with_dora() -> None:
    assert log_dir().name == "Dora"


def test_setup_logging_idempotent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    logger1 = setup_logging(background=True)
    handler_count = len(logger1.handlers)
    logger2 = setup_logging(background=True)
    assert logger1 is logger2
    assert len(logger2.handlers) == handler_count
    assert logger2.level == logging.DEBUG
