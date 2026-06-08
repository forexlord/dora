from core.intent.prompts import (
    PROMPT_VERSION,
    build_chat_system_prompt,
    build_resolve_system_prompt,
)


def test_prompts_non_empty() -> None:
    assert PROMPT_VERSION
    assert "Dora" in build_resolve_system_prompt()
    assert "volume_status" in build_resolve_system_prompt()
    assert "Dora" in build_chat_system_prompt()
