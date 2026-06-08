
from core.intent.parser import IntentParser


def test_parser_rule_open_beats_llm() -> None:
    parser = IntentParser(
        model_path="models/test.gguf",
        config={"llama_server_port": 8765},
        use_llm_fallback=False,
    )
    intent = parser.parse("please open notepad")
    assert intent == {"type": "open", "app": "notepad"}


def test_parser_profanity_refusal() -> None:
    parser = IntentParser(
        model_path="models/test.gguf",
        config={"llama_server_port": 8765},
        use_llm_fallback=False,
    )
    intent = parser.parse("fuck you")
    assert intent.get("type") == "chat"
    assert "can't help" in intent.get("reply", "").lower()
