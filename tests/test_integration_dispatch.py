from unittest.mock import MagicMock

from core.assistant.mixins.dispatch import DispatchMixin
from core.config import DoraConfig
from core.session import SessionState


class _FakeHost(DispatchMixin):
    def __init__(self) -> None:
        self._user_cancelled = False
        self._overlay_user_hidden = False
        self._overlay = MagicMock()
        self._use_llm = False
        self._allow_chat_fallback = False
        self._llm_ready = True
        self._config = DoraConfig()
        self._parser = MagicMock()
        self._executor = MagicMock()
        self._listener = None
        self._wake_word_enabled = False
        self._post_response_listen_window_sec = 8.0
        self._speak_calls: list[str] = []

    def _sync_overlay_for_session(self, _state: SessionState) -> None:
        pass

    def _set_overlay_phase(self, _phase: str) -> None:
        pass

    def _confirm_action(self, _prompt: str) -> bool:
        return True

    def _speak_with_overlay(self, message: str, _state: SessionState) -> None:
        self._speak_calls.append(message)


def test_dispatch_system_volume_mute(monkeypatch) -> None:
    host = _FakeHost()
    host._parser.parse.return_value = {"type": "volume_mute"}
    state = SessionState()

    monkeypatch.setattr(
        "core.assistant.mixins.dispatch.apply_system_intent",
        lambda _intent: (True, "Muted."),
    )

    host._dispatch_turn("mute", state)
    assert "Muted." in host._speak_calls


def test_dispatch_open_app(monkeypatch) -> None:
    host = _FakeHost()
    host._parser.parse.return_value = {"type": "open", "app": "notepad"}
    host._executor.open_app.return_value = (True, "Okay, I opened notepad.")
    state = SessionState()

    host._dispatch_turn("open notepad", state)
    host._executor.open_app.assert_called_once()
    assert "notepad" in host._speak_calls[0].lower()


def test_dispatch_clarify_sets_pending_followup() -> None:
    host = _FakeHost()
    host._parser.parse.return_value = {
        "type": "clarify",
        "reply": "How much louder?",
        "pending": "volume",
    }
    state = SessionState()
    host._dispatch_turn("louder", state)
    assert state.pending_followup is not None
    assert state.pending_followup["pending"] == "volume"


def test_dispatch_chat_remembers_turn() -> None:
    host = _FakeHost()
    host._parser.parse.return_value = {"type": "chat", "reply": "Sure thing."}
    state = SessionState()
    host._dispatch_turn("tell me a joke", state)
    assert len(state.chat_turns) == 1
    assert "Sure thing." in host._speak_calls[0]
