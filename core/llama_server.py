"""Bundled llama.cpp server (no Ollama, no llama-cpp-python compile)."""

from __future__ import annotations

import atexit
import json
import os
import platform
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from core.win_subprocess import popen_no_console

DEFAULT_LLAMA_RELEASE = "b9509"
DEFAULT_LLAMA_ZIP_URL_X64 = (
    f"https://github.com/ggml-org/llama.cpp/releases/download/{DEFAULT_LLAMA_RELEASE}/"
    f"llama-{DEFAULT_LLAMA_RELEASE}-bin-win-cpu-x64.zip"
)
DEFAULT_LLAMA_ZIP_URL_ARM64 = (
    f"https://github.com/ggml-org/llama.cpp/releases/download/{DEFAULT_LLAMA_RELEASE}/"
    f"llama-{DEFAULT_LLAMA_RELEASE}-bin-win-cpu-arm64.zip"
)
DEFAULT_LLAMA_TOOLS_DIR = "tools/llama-cpp"

_server_proc: Any = None
_server_port: int | None = None
_server_model: str | None = None
_last_error: str | None = None


def last_server_error() -> str | None:
    return _last_error


def default_llama_zip_url() -> str:
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return DEFAULT_LLAMA_ZIP_URL_ARM64
    return DEFAULT_LLAMA_ZIP_URL_X64


def llama_tools_dir_from_config(config: dict) -> Path:
    return Path(str(config.get("llama_tools_dir", DEFAULT_LLAMA_TOOLS_DIR)))


def find_llama_executable(tools_dir: Path, names: tuple[str, ...]) -> Path | None:
    if not tools_dir.exists():
        return None
    for name in names:
        direct = tools_dir / name
        if direct.is_file():
            return direct
    for path in tools_dir.rglob(name):
        if path.is_file():
            return path
    return None


def resolve_llama_server_exe(config: dict) -> Path | None:
    custom = str(config.get("llama_server_exe", "")).strip()
    if custom:
        p = Path(custom).expanduser()
        return p if p.is_file() else None
    tools = llama_tools_dir_from_config(config)
    return find_llama_executable(tools, ("llama-server.exe", "llama-server"))


def ensure_llama_tools(config: dict) -> tuple[bool, str]:
    tools_dir = llama_tools_dir_from_config(config)
    if resolve_llama_server_exe(config) is not None:
        return True, f"llama.cpp tools ready at: {tools_dir}"

    if not bool(config.get("auto_download_llama_tools", True)):
        return False, f"llama.cpp tools not found in {tools_dir} and auto download is disabled."

    url = str(config.get("llama_tools_url", "")).strip() or default_llama_zip_url()
    tools_dir.mkdir(parents=True, exist_ok=True)
    zip_path = tools_dir / "llama-tools-download.zip"

    try:
        with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310
            with zip_path.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 512)
                    if not chunk:
                        break
                    output.write(chunk)
    except Exception as exc:
        return False, f"Failed to download llama.cpp tools: {exc}"

    import zipfile

    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(tools_dir)
    except Exception as exc:
        return False, f"Failed to extract llama.cpp tools: {exc}"
    finally:
        zip_path.unlink(missing_ok=True)

    exe = resolve_llama_server_exe(config)
    if exe is None:
        return False, f"Download finished but llama-server.exe was not found under {tools_dir}"
    return True, f"Downloaded llama.cpp tools to: {tools_dir}"


def _health_ok(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as resp:  # noqa: S310
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def stop_llama_server() -> None:
    global _server_proc, _server_port, _server_model
    if _server_proc is not None and _server_proc.poll() is None:
        try:
            _server_proc.terminate()
            _server_proc.wait(timeout=10)
        except Exception:
            try:
                _server_proc.kill()
            except Exception:
                pass
    _server_proc = None
    _server_port = None
    _server_model = None


atexit.register(stop_llama_server)


def start_llama_server(
    config: dict,
    model_path: str,
    *,
    port: int | None = None,
    startup_timeout_sec: int = 600,
) -> bool:
    global _server_proc, _server_port, _server_model, _last_error

    exe = resolve_llama_server_exe(config)
    if exe is None:
        _last_error = "llama-server.exe not found. Re-run Install-Dora.bat to download tools."
        return False

    model = str(Path(model_path).expanduser().resolve())
    if not Path(model).is_file():
        _last_error = f"GGUF model not found: {model}"
        return False

    listen_port = int(port or config.get("llama_server_port", 8765))
    if (
        _server_proc is not None
        and _server_proc.poll() is None
        and _server_port == listen_port
        and _server_model == model
        and _health_ok(listen_port)
    ):
        _last_error = None
        return True

    stop_llama_server()

    n_ctx = int(config.get("llm_n_ctx", 4096))
    threads = int(config.get("llm_n_threads", 0))
    thread_arg = str(threads if threads > 0 else max(1, (os.cpu_count() or 4)))

    cmd = [
        str(exe),
        "-m",
        model,
        "--host",
        "127.0.0.1",
        "--port",
        str(listen_port),
        "--log-disable",
        "-c",
        str(n_ctx),
        "-t",
        thread_arg,
    ]
    try:
        _server_proc = popen_no_console(
            cmd,
            cwd=str(exe.parent),
            stdout=subprocess.DEVNULL,  # type: ignore[name-defined]
            stderr=subprocess.DEVNULL,  # type: ignore[name-defined]
        )
    except Exception as exc:
        _last_error = f"Failed to start llama-server: {exc}"
        return False

    _server_port = listen_port
    _server_model = model

    deadline = time.time() + max(60, int(startup_timeout_sec))
    while time.time() < deadline:
        if _server_proc.poll() is not None:
            _last_error = "llama-server exited during startup."
            return False
        if _health_ok(listen_port):
            _last_error = None
            return True
        time.sleep(1.0)

    _last_error = "llama-server did not become ready in time (large model on CPU can take several minutes)."
    return False


# subprocess only imported for DEVNULL
def _post_json(port: int, path: str, body: dict[str, Any], timeout: int = 180) -> dict[str, Any] | None:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def chat_completion(
    port: int,
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
    json_object: bool = False,
) -> str | None:
    body: dict[str, Any] = {
        "messages": messages,
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
        "stream": False,
    }
    if json_object:
        body["response_format"] = {"type": "json_object"}
    data = _post_json(port, "/v1/chat/completions", body)
    if not isinstance(data, dict):
        return None
    choices = data.get("choices") or []
    if not choices:
        return None
    msg = choices[0].get("message") or {}
    return str(msg.get("content", "")).strip() or None


def text_completion(
    port: int,
    prompt: str,
    *,
    max_tokens: int,
    temperature: float,
) -> str | None:
    body: dict[str, Any] = {
        "prompt": prompt,
        "n_predict": int(max_tokens),
        "temperature": float(temperature),
        "stream": False,
    }
    data = _post_json(port, "/completion", body)
    if not isinstance(data, dict):
        return None
    return str(data.get("content", "")).strip() or None


def probe_server_load(config: dict, model_path: str) -> tuple[bool, str]:
    port = int(config.get("llama_server_port", 8765))
    if not start_llama_server(config, model_path, port=port, startup_timeout_sec=600):
        return False, last_server_error() or "Could not start llama-server."
    out = chat_completion(
        port,
        [
            {"role": "system", "content": 'Reply JSON only: {"type":"chat","reply":"ok"}'},
            {"role": "user", "content": "ping"},
        ],
        max_tokens=16,
        temperature=0.0,
        json_object=True,
    )
    if not out:
        return False, last_server_error() or "llama-server returned no output."
    return True, "OK"
