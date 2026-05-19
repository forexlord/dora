from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from urllib.request import urlopen

from core.win_subprocess import run_no_console


DEFAULT_VOSK_URL = (
    "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
)


def _resolve_ollama_bin() -> str | None:
    binary = shutil.which("ollama")
    if binary:
        return binary
    local_app = Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe"
    if local_app.exists():
        return str(local_app)
    program_files = Path("C:/Program Files/Ollama/ollama.exe")
    if program_files.exists():
        return str(program_files)
    return None


def ensure_runtime_files() -> None:
    Path("apps").mkdir(parents=True, exist_ok=True)
    defaults: dict[str, str] = {
        "permissions.json": "{}",
    }
    for filename, content in defaults.items():
        path = Path(filename)
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def _looks_like_vosk_model(path: Path) -> bool:
    expected_items = {"am", "conf", "graph"}
    if not path.exists() or not path.is_dir():
        return False
    present = {p.name for p in path.iterdir()}
    return expected_items.issubset(present)


def _find_first_model_dir(root: Path) -> Path | None:
    if _looks_like_vosk_model(root):
        return root
    if not root.exists() or not root.is_dir():
        return None
    for child in root.iterdir():
        if child.is_dir() and _looks_like_vosk_model(child):
            return child
    return None


def ensure_vosk_model(config: dict) -> tuple[bool, str, str | None]:
    if not bool(config.get("auto_download_vosk_model", True)):
        return False, "Auto model download disabled by config.", None

    model_path = Path(str(config.get("vosk_model_path", "models/vosk-model")))
    existing = _find_first_model_dir(model_path)
    if existing is not None:
        if existing != model_path:
            return True, f"Using discovered Vosk model at: {existing}", existing.as_posix()
        return True, f"Vosk model already present at: {model_path}", None

    model_url = str(config.get("vosk_model_url", DEFAULT_VOSK_URL)).strip()
    models_root = model_path.parent
    models_root.mkdir(parents=True, exist_ok=True)
    model_path.mkdir(parents=True, exist_ok=True)
    zip_path = models_root / "vosk-model-download.zip"

    try:
        with urlopen(model_url, timeout=60) as response:  # noqa: S310
            with zip_path.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    output.write(chunk)
    except Exception as exc:
        return False, f"Failed to download Vosk model: {exc}", None

    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(models_root)
    except Exception as exc:
        return False, f"Failed to extract Vosk model archive: {exc}", None
    finally:
        if zip_path.exists():
            zip_path.unlink(missing_ok=True)

    discovered = _find_first_model_dir(model_path) or _find_first_model_dir(models_root)
    if discovered is None:
        return False, "Model downloaded but no valid Vosk folder was found after extraction.", None

    return True, f"Downloaded and prepared Vosk model at: {discovered}", discovered.as_posix()


def ensure_ollama_runtime(config: dict) -> tuple[bool, str]:
    ollama_bin = _resolve_ollama_bin()
    if ollama_bin:
        return True, f"Ollama detected at: {ollama_bin}"

    if not bool(config.get("auto_install_ollama", True)):
        return False, "Ollama not found and auto-install is disabled."

    install_cmd = "irm https://ollama.com/install.ps1 | iex"
    try:
        result = run_no_console(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", install_cmd],
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
    except Exception as exc:
        return False, f"Failed to run Ollama installer: {exc}"

    if result.returncode != 0:
        return False, f"Ollama installer returned code {result.returncode}."

    ollama_bin = _resolve_ollama_bin()
    if not ollama_bin:
        return False, "Installer finished but `ollama` is not available in PATH yet."
    return True, f"Ollama installed at: {ollama_bin}"


def ensure_ollama_model(config: dict) -> tuple[bool, str]:
    model_name = str(config.get("ollama_model", "phi")).strip()
    if not model_name:
        return False, "No Ollama model configured."

    if not bool(config.get("auto_pull_ollama_model", True)):
        return True, f"Auto model pull disabled. Using configured model: {model_name}"

    ollama_bin = _resolve_ollama_bin()
    if not ollama_bin:
        return False, "Ollama binary not found while checking models."

    try:
        list_result = run_no_console(
            [ollama_bin, "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except Exception as exc:
        return False, f"Failed to query Ollama models: {exc}"

    if list_result.returncode == 0 and model_name in list_result.stdout:
        return True, f"Ollama model already present: {model_name}"

    pull_result = run_no_console(
        [ollama_bin, "pull", model_name],
        capture_output=True,
        text=True,
        check=False,
        timeout=1200,
    )
    if pull_result.returncode != 0:
        return False, f"Failed to pull Ollama model: {model_name}"

    return True, f"Ollama model ready: {model_name}"


def persist_config(config: dict, path: str = "config.json") -> None:
    Path(path).write_text(json.dumps(config, indent=2), encoding="utf-8")
