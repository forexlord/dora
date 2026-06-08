from core.config import DoraConfig
from core.executor import CommandExecutor
from core.permissions import PermissionStore


def test_dora_config_trust_mapped_apps_defaults_false() -> None:
    cfg = DoraConfig()
    assert cfg.trust_mapped_apps is False


def test_executor_trust_mapped_apps_defaults_false(tmp_path) -> None:
    store = PermissionStore(tmp_path / "permissions.json")
    executor = CommandExecutor(permission_store=store, apps_dir=tmp_path / "apps")
    assert executor.trust_mapped_apps is False
