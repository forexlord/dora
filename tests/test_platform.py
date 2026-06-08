import pytest

from core.platform_check import require_windows


def test_require_windows_passes_on_win32(monkeypatch) -> None:
    monkeypatch.setattr("core.platform_check.sys.platform", "win32")
    require_windows()


def test_require_windows_exits_elsewhere(monkeypatch) -> None:
    monkeypatch.setattr("core.platform_check.sys.platform", "linux")
    with pytest.raises(SystemExit):
        require_windows()
