from unittest.mock import patch

from core.status_overlay import NullStatusOverlay, build_status_overlay


def test_null_overlay_noop() -> None:
    overlay = NullStatusOverlay()
    assert overlay.start() is False
    assert overlay.active is False
    overlay.set_phase("listening")
    overlay.show()
    overlay.hide()
    overlay.shutdown()


def test_build_status_overlay_disabled() -> None:
    overlay = build_status_overlay(False, "hey dora")
    assert isinstance(overlay, NullStatusOverlay)


def test_build_status_overlay_without_tkinter() -> None:
    with patch.dict("sys.modules", {"tkinter": None}):
        overlay = build_status_overlay(True, "hey dora")
    assert isinstance(overlay, NullStatusOverlay)
