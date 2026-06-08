from core.app_resolve import resolve_app_key


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
