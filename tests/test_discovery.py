from core.discovery import normalize_app_name


def test_normalize_app_name() -> None:
    assert normalize_app_name("  Google-Chrome ") == "google chrome"
    assert normalize_app_name("File_Explorer") == "file explorer"
