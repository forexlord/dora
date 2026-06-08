import json
from unittest.mock import patch

from core.llama_server import (
    LlamaServerManager,
    _health_ok,
    _post_json,
    chat_completion,
)


def test_health_ok_true() -> None:
    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch("core.llama_server.urllib.request.urlopen", return_value=Resp()):
        assert _health_ok(8765) is True


def test_post_json_parses_response() -> None:
    payload = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

    class Resp:
        def read(self):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch("core.llama_server.urllib.request.urlopen", return_value=Resp()):
        data = _post_json(8765, "/v1/chat/completions", {"messages": []})
        assert data is not None
        out = chat_completion(
            8765,
            [{"role": "user", "content": "hi"}],
            max_tokens=8,
            temperature=0.0,
        )
        assert out == "ok"


def test_llama_server_manager_tracks_error() -> None:
    mgr = LlamaServerManager()
    with patch("core.llama_server.resolve_llama_server_exe", return_value=None):
        assert mgr.start({}, "missing.gguf") is False
        assert mgr.last_error is not None
