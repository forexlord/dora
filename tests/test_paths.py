import json
from pathlib import Path

import pytest

from core.paths import load_json, resolve_working_directory


def test_load_json_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"wake_word": "dora"}), encoding="utf-8")
    data = load_json(path)
    assert data["wake_word"] == "dora"


def test_load_json_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_json(tmp_path / "missing.json")


def test_resolve_working_directory_dora_home(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DORA_HOME", str(tmp_path))
    root = resolve_working_directory()
    assert root == tmp_path.resolve()
    assert root.exists()


def test_resolve_working_directory_voice_assistant_home_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("DORA_HOME", raising=False)
    monkeypatch.setenv("VOICE_ASSISTANT_HOME", str(tmp_path))
    root = resolve_working_directory()
    assert root == tmp_path.resolve()


def test_resolve_working_directory_cwd(monkeypatch) -> None:
    monkeypatch.delenv("DORA_HOME", raising=False)
    monkeypatch.delenv("VOICE_ASSISTANT_HOME", raising=False)
    root = resolve_working_directory()
    assert root == Path.cwd().resolve()
