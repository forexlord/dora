from pathlib import Path
from unittest.mock import MagicMock, patch

from core.llama_server import LlamaServerManager


@patch("core.llama_server._health_ok", return_value=True)
@patch("core.llama_server.popen_no_console")
@patch("core.llama_server.resolve_llama_server_exe")
def test_llama_manager_starts_subprocess(
    mock_resolve: MagicMock,
    mock_popen: MagicMock,
    _mock_health: MagicMock,
    tmp_path: Path,
) -> None:
    exe = tmp_path / "llama-server.exe"
    exe.write_bytes(b"stub")
    model = tmp_path / "model.gguf"
    model.write_bytes(b"gguf")

    proc = MagicMock()
    proc.poll.return_value = None
    mock_popen.return_value = proc
    mock_resolve.return_value = exe

    mgr = LlamaServerManager()
    ok = mgr.start({"llm_n_ctx": 512, "llama_server_port": 8765}, str(model))
    assert ok is True
    assert mgr.port == 8765
    assert mgr.model == str(model.resolve())
    mock_popen.assert_called_once()
    cmd = mock_popen.call_args[0][0]
    assert str(exe) in cmd
    assert str(model.resolve()) in cmd


@patch("core.llama_server._health_ok", return_value=True)
def test_llama_manager_reuses_healthy_process(_mock_health: MagicMock, tmp_path: Path) -> None:
    mgr = LlamaServerManager()
    mgr.proc = MagicMock()
    mgr.proc.poll.return_value = None
    mgr.port = 8765
    mgr.model = str((tmp_path / "m.gguf").resolve())
    (tmp_path / "m.gguf").write_bytes(b"x")

    with patch("core.llama_server.resolve_llama_server_exe") as mock_resolve:
        exe = tmp_path / "llama-server.exe"
        exe.write_bytes(b"stub")
        mock_resolve.return_value = exe
        ok = mgr.start({}, str(tmp_path / "m.gguf"))
    assert ok is True
