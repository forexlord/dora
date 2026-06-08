from pathlib import Path

from core.permissions import PermissionStore


def test_permission_store_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "permissions.json"
    store = PermissionStore(str(path))
    assert not store.is_allowed("chrome")
    store.set_allowed("chrome", True)
    assert store.is_allowed("chrome")
    reloaded = PermissionStore(str(path))
    assert reloaded.is_allowed("chrome")


def test_permission_store_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "permissions.json"
    path.write_text("{not json", encoding="utf-8")
    store = PermissionStore(str(path))
    assert not store.is_allowed("anything")
