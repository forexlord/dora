from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path
from urllib.request import urlopen

from core.llama_runtime import gguf_header_valid
from core.llama_server import ensure_llama_tools  # noqa: F401 — used by install/setup

DEFAULT_VOSK_URL = (
    "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
)

DEFAULT_LLM_URL = (
    "https://huggingface.co/bartowski/Phi-3-mini-4k-instruct-GGUF/resolve/main/"
    "Phi-3-mini-4k-instruct-Q4_K_M.gguf"
)
DEFAULT_LLM_PATH = "models/Phi-3-mini-4k-instruct-Q4_K_M.gguf"
_MIN_GGUF_BYTES = 50_000_000
logger = logging.getLogger("dora.bootstrap")


def llm_model_path_from_config(config: dict | object) -> str:
    from core.config import DoraConfig

    if isinstance(config, DoraConfig):
        path = config.llm_model_path.strip()
    else:
        path = str(config.get("llm_model_path", "")).strip()  # type: ignore[union-attr]
    if path:
        return path
    return DEFAULT_LLM_PATH


def config_use_llm_fallback(config: dict) -> bool:
    from core.config import DoraConfig, migrate_legacy_keys

    if isinstance(config, DoraConfig):
        return config.use_llm_fallback
    data = migrate_legacy_keys(config)
    return bool(data.get("use_llm_fallback", True))


def ensure_runtime_files() -> None:
    Path("apps").mkdir(parents=True, exist_ok=True)
    Path("models").mkdir(parents=True, exist_ok=True)
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


def _valid_gguf_file(path: Path) -> bool:
    return (
        path.is_file()
        and path.stat().st_size >= _MIN_GGUF_BYTES
        and gguf_header_valid(path)
    )


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


def ensure_llm_model(config: dict) -> tuple[bool, str]:
    model_path = Path(llm_model_path_from_config(config))
    if model_path.is_file() and not gguf_header_valid(model_path):
        try:
            model_path.unlink(missing_ok=True)
        except OSError:
            return False, (
                f"Language model at {model_path} is not a valid GGUF file. "
                "Delete it manually and re-run setup."
            )
    if _valid_gguf_file(model_path):
        return True, f"Language model ready: {model_path}"

    from core.config import DoraConfig, migrate_legacy_keys

    raw = config.to_dict() if isinstance(config, DoraConfig) else config
    data = migrate_legacy_keys(raw)
    auto = data.get("auto_download_llm_model", True)
    if not bool(auto):
        return (
            False,
            f"GGUF model not found at {model_path} and auto_download_llm_model is disabled.",
        )

    model_url = str(data.get("llm_model_url", DEFAULT_LLM_URL)).strip()
    if not model_url:
        return False, "No llm_model_url configured for download."

    model_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = model_path.with_suffix(model_path.suffix + ".part")

    try:
        with urlopen(model_url, timeout=120) as response:  # noqa: S310
            total = int(response.headers.get("Content-Length", 0) or 0)
            downloaded = 0
            last_mb = 0
            with tmp_path.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 512)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        mb = downloaded // (1024 * 1024)
                        if mb >= last_mb + 50:
                            pct = min(100, int(100 * downloaded / total))
                            logger.info("Downloaded %s MB (%s%%)", mb, pct)
                            last_mb = mb
        tmp_path.replace(model_path)
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return False, f"Failed to download language model: {exc}"

    if not _valid_gguf_file(model_path):
        return False, f"Download finished but file looks invalid: {model_path}"

    return True, f"Downloaded language model to: {model_path}"


def persist_config(config: dict, path: str = "config.json") -> None:
    Path(path).write_text(json.dumps(config, indent=2), encoding="utf-8")
