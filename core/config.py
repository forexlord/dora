"""Typed application configuration with legacy key migration and validation."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

logger = logging.getLogger("dora.config")

_LEGACY_KEY_ALIASES: dict[str, str] = {
    "ollama_num_ctx": "llm_n_ctx",
    "ollama_num_predict_resolve": "llm_num_predict_resolve",
    "ollama_num_predict_chat": "llm_num_predict_chat",
    "ollama_temperature_resolve": "llm_temperature_resolve",
    "ollama_fast_chat_path": "llm_fast_chat_path",
    "use_ollama_fallback": "use_llm_fallback",
    "warmup_ollama_on_start": "warmup_llm_on_start",
    "auto_pull_ollama_model": "auto_download_llm_model",
    "wake_word_timeout_sec": "voice_session_after_wake_sec",
}


class ConfigValidationError(ValueError):
    """Raised when config.json contains invalid values."""


def migrate_legacy_keys(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Copy config and promote deprecated Ollama-era keys to current names."""
    data = dict(raw)
    for legacy, current in _LEGACY_KEY_ALIASES.items():
        if legacy in data and current not in data:
            data[current] = data[legacy]
    return data


def config_to_runtime_dict(config: DoraConfig | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(config, DoraConfig):
        return config.to_dict()
    return migrate_legacy_keys(config)


@dataclass
class DoraConfig:
    language: str = "en"
    sample_rate: int = 16000
    audio_input_device: int | str | None = None
    audio_stream_retries: int = 4
    stt_engine: str = "vosk"
    vosk_model_path: str = "models/vosk-model-small-en-us-0.15"
    auto_download_vosk_model: bool = True
    vosk_model_url: str = (
        "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
    )
    vosk_idle_rms_threshold: float = 520.0
    show_processing_on_speech_pause: bool = True
    speech_pause_to_processing_sec: float = 0.42
    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = "default"
    whisper_language: str = "en"
    whisper_end_silence_sec: float = 0.85
    whisper_max_utterance_sec: float = 45.0
    whisper_initial_prompt: str = (
        "wake words include Dora and hey Dora. Voice assistant commands."
    )
    show_status_overlay: bool = True
    wake_word_enabled: bool = True
    wake_word: str = "dora"
    wake_phrases: list[str] = field(default_factory=list)
    wake_prefix_aliases: list[str] = field(default_factory=list)
    wake_hint: str = ""
    announce_ready_at_startup: bool = True
    ready_message: str = (
        "Dora is ready. Say Dora or hey Dora when you need me."
    )
    voice_session_after_wake_sec: int = 120
    voice_processing_grace_sec: int = 180
    voice_idle_timeout_sec: float = 10.0
    post_response_listen_window_sec: int = 10
    chat_memory_turns: int = 4
    confirm_shutdown: bool = True
    use_llm_fallback: bool = True
    llm_fast_chat_path: bool = True
    llm_num_predict_resolve: int = 56
    llm_num_predict_chat: int = 72
    llm_temperature_resolve: float = 0.0
    llm_n_ctx: int = 4096
    llm_n_threads: int = 0
    llm_model_path: str = "models/Phi-3-mini-4k-instruct-Q4_K_M.gguf"
    llm_model_url: str = (
        "https://huggingface.co/bartowski/Phi-3-mini-4k-instruct-GGUF/resolve/main/"
        "Phi-3-mini-4k-instruct-Q4_K_M.gguf"
    )
    auto_download_llm_model: bool = True
    llama_tools_dir: str = "tools/llama-cpp"
    llama_tools_url: str = ""
    auto_download_llama_tools: bool = True
    llama_server_port: int = 8765
    warmup_llm_on_start: bool = True
    speak_responses: bool = True
    tts_rate: int = 0
    tts_volume: int = 70
    tts_voice: str = "zira"
    allow_text_fallback: bool = True
    allow_chat_fallback: bool = True
    auto_discover_apps: bool = True
    trust_mapped_apps: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], *, strict: bool = False) -> DoraConfig:
        data = migrate_legacy_keys(raw)
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            msg = f"Unknown config keys ignored: {', '.join(unknown)}"
            if strict:
                raise ConfigValidationError(msg)
            logger.warning(msg)
        kwargs = {key: data[key] for key in known if key in data}
        cfg = cls(**kwargs)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        errors: list[str] = []
        if self.sample_rate < 8000 or self.sample_rate > 48000:
            errors.append(f"sample_rate must be 8000–48000, got {self.sample_rate}")
        if self.stt_engine.strip().lower() not in {"vosk", "whisper"}:
            errors.append(f'stt_engine must be "vosk" or "whisper", got {self.stt_engine!r}')
        if self.voice_session_after_wake_sec < 5:
            errors.append("voice_session_after_wake_sec must be >= 5")
        if self.voice_idle_timeout_sec < 1:
            errors.append("voice_idle_timeout_sec must be >= 1")
        if self.chat_memory_turns < 1 or self.chat_memory_turns > 12:
            errors.append("chat_memory_turns must be 1–12")
        if self.llm_n_ctx < 512 or self.llm_n_ctx > 131072:
            errors.append("llm_n_ctx must be 512–131072")
        if self.llama_server_port < 1024 or self.llama_server_port > 65535:
            errors.append("llama_server_port must be 1024–65535")
        if self.tts_volume < 0 or self.tts_volume > 100:
            errors.append("tts_volume must be 0–100")
        if errors:
            raise ConfigValidationError("; ".join(errors))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def llm_n_ctx_or_none(self) -> int | None:
        return self.llm_n_ctx if self.llm_n_ctx > 0 else None


def load_dora_config(path: str | Path, *, strict: bool = False) -> DoraConfig:
    from core.paths import load_json

    return DoraConfig.from_mapping(load_json(Path(path)), strict=strict)
