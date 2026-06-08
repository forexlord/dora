from pathlib import Path
from unittest.mock import patch

from core.llama_runtime import gguf_header_valid, probe_llama_load


def test_gguf_header_valid_true(tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"GGUF" + b"\x00" * 8)
    assert gguf_header_valid(model) is True


def test_gguf_header_valid_false_for_missing_file(tmp_path: Path) -> None:
    assert gguf_header_valid(tmp_path / "nope.gguf") is False


def test_gguf_header_valid_false_for_bad_magic(tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"BAD!")
    assert gguf_header_valid(model) is False


@patch("core.llama_runtime.probe_server_load", return_value=(True, "ready"))
def test_probe_llama_load_delegates(mock_probe) -> None:
    ok, msg = probe_llama_load("model.gguf", {"llama_server_port": 8765})
    assert ok is True
    assert msg == "ready"
    mock_probe.assert_called_once()
