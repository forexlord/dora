from core.session import (
    SessionState,
    build_chat_followup_context,
    clear_chat_context,
    heard_is_confirmation,
    remember_chat_turn,
)


def test_multi_turn_chat_memory() -> None:
    state = SessionState()
    remember_chat_turn(state, "hello", "Hi there.", max_turns=3)
    remember_chat_turn(state, "what is two plus two", "Four.", max_turns=3)
    remember_chat_turn(state, "and three", "Seven in total.", max_turns=3)
    assert len(state.chat_turns) == 3
    ctx = build_chat_followup_context(state, "tell me more", max_turns=3)
    assert ctx is not None
    assert "Four." in ctx
    assert "Seven in total." in ctx
    assert "tell me more" in ctx


def test_chat_memory_trim() -> None:
    state = SessionState()
    for i in range(5):
        remember_chat_turn(state, f"u{i}", f"a{i}", max_turns=2)
    assert len(state.chat_turns) == 2
    assert state.chat_turns[0].user == "u3"


def test_heard_is_confirmation() -> None:
    assert heard_is_confirmation("yes")
    assert heard_is_confirmation("yeah please")
    assert not heard_is_confirmation("no")


def test_clear_chat_context() -> None:
    state = SessionState()
    remember_chat_turn(state, "hi", "hello")
    clear_chat_context(state)
    assert state.chat_turns == []
