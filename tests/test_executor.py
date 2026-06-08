from pathlib import Path

from core.executor import CommandExecutor
from core.permissions import PermissionStore


def test_open_app_trust_mapped_apps(tmp_path: Path, monkeypatch) -> None:
    store = PermissionStore(str(tmp_path / "permissions.json"))
    executor = CommandExecutor(
        store,
        apps_dir=tmp_path / "apps",
        auto_discover_apps=False,
        trust_mapped_apps=True,
    )
    index = {"chrome": str(tmp_path / "chrome.exe")}
    (tmp_path / "chrome.exe").write_text("", encoding="utf-8")

    monkeypatch.setattr(executor, "_get_launch_index", lambda: index)
    monkeypatch.setattr(executor, "_launch_target", lambda _t: None)

    ok, msg = executor.open_app("chrome")
    assert ok is True
    assert store.is_allowed("chrome")


def test_open_app_permission_denied(tmp_path: Path, monkeypatch) -> None:
    store = PermissionStore(str(tmp_path / "permissions.json"))
    executor = CommandExecutor(
        store,
        apps_dir=tmp_path / "apps",
        auto_discover_apps=False,
        trust_mapped_apps=False,
    )
    index = {"chrome": str(tmp_path / "chrome.exe")}
    (tmp_path / "chrome.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(executor, "_get_launch_index", lambda: index)
    monkeypatch.setattr(executor, "_confirm", lambda *_a, **_k: False)

    ok, msg = executor.open_app("chrome")
    assert ok is False
    assert "denied" in msg.lower()
