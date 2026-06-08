import subprocess
from unittest.mock import MagicMock, patch

from core.win_subprocess import popen_no_console, run_no_console


@patch("core.win_subprocess.subprocess.Popen")
def test_popen_no_console(mock_popen: MagicMock) -> None:
    mock_popen.return_value = MagicMock()
    proc = popen_no_console(["echo", "hi"])
    assert proc is mock_popen.return_value
    mock_popen.assert_called_once()


@patch("core.win_subprocess.subprocess.run")
def test_run_no_console(mock_run: MagicMock) -> None:
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
    result = run_no_console(["netsh", "help"], capture_output=True, text=True)
    assert result.returncode == 0
    mock_run.assert_called_once()
