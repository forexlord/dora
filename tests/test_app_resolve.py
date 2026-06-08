from core.app_resolve import apply_app_alias, resolve_app_key


def test_resolve_exact_match() -> None:
    key, score = resolve_app_key("chrome", {"chrome": "C:/Apps/chrome.exe"})
    assert key == "chrome"
    assert score == 1.0


def test_resolve_fuzzy_match() -> None:
    candidates = {
        "google chrome": "C:/Apps/chrome.exe",
        "microsoft edge": "C:/Apps/msedge.exe",
    }
    key, score = resolve_app_key("googl chrome", candidates)
    assert key == "google chrome"
    assert score >= 0.42


def test_resolve_no_candidates() -> None:
    key, score = resolve_app_key("chrome", {})
    assert key is None
    assert score == 0.0


def test_apply_app_alias_file_manager() -> None:
    assert apply_app_alias("file manager") == "file explorer"


def test_apply_app_alias_brave_mishearings() -> None:
    assert apply_app_alias("breathe") == "brave"
    assert apply_app_alias("brief") == "brave"


def test_was_up_alias_maps_to_whatsapp() -> None:
    assert apply_app_alias("was up") == "whatsapp"


def test_file_manager_does_not_match_task_manager() -> None:
    candidates = {
        "task manager": r"C:\Windows\System32\Taskmgr.exe",
        "file explorer": r"C:\Windows\explorer.exe",
    }
    key, _score = resolve_app_key("file manager", candidates)
    assert key != "task manager"
    assert apply_app_alias("file manager") == "file explorer"
