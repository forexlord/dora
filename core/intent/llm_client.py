"""Local GGUF inference via bundled llama-server (one installer, no Visual Studio, no Ollama)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from core.llama_server import (
    chat_completion,
    last_server_error,
    start_llama_server,
)

from .constants import (
    BAD_CLARIFY_SUBSTRINGS,
    REFUSAL_REPLY,
    VALID_CLARIFY_PENDING,
)
from .prompts import build_chat_system_prompt, build_resolve_system_prompt
from .safety import contains_profanity, sanitize_reply_text

logger = logging.getLogger("dora.llm")


def last_llama_load_error() -> str | None:
    return last_server_error()


def coerce_json_number(val: Any) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, int | float):
        return float(val)
    if isinstance(val, str):
        s = val.strip().replace("%", "")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def parse_resolve_json(content: str) -> dict[str, Any] | None:
    content = content.strip()
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", content)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


class GgufIntentBackend:
    """HTTP client to bundled llama-server for JSON intents and chat replies."""

    def __init__(
        self,
        model_path: str,
        config: dict[str, Any],
        *,
        num_predict_resolve: int = 120,
        num_predict_chat: int = 128,
        temperature_resolve: float = 0.0,
        n_ctx: int | None = None,
        n_threads: int = 0,
    ) -> None:
        self._model_path = str(model_path).strip()
        merged = dict(config)
        if n_ctx is not None and int(n_ctx) > 0:
            merged["llm_n_ctx"] = int(n_ctx)
        if n_threads > 0:
            merged["llm_n_threads"] = int(n_threads)
        self._config = merged
        self._num_predict_resolve = max(24, int(num_predict_resolve))
        self._num_predict_chat = max(32, min(int(num_predict_chat), 160))
        self._temperature_resolve = float(temperature_resolve)
        self._port = int(merged.get("llama_server_port", 8765))
        self._server_ready = False

    def _ensure_running(self) -> bool:
        if self._server_ready and start_llama_server(
            self._config, self._model_path, port=self._port
        ):
            return True
        ok = start_llama_server(self._config, self._model_path, port=self._port)
        self._server_ready = ok
        if not ok:
            logger.error("llama-server failed to start: %s", last_server_error())
        return ok

    def available(self) -> bool:
        from pathlib import Path

        return Path(self._model_path).expanduser().is_file()

    def warmup(self) -> bool:
        if not self._ensure_running():
            return False
        try:
            out = chat_completion(
                self._port,
                [
                    {
                        "role": "system",
                        "content": 'Reply JSON only: {"type":"chat","reply":"ok"}',
                    },
                    {"role": "user", "content": "ping"},
                ],
                max_tokens=16,
                temperature=0.0,
                json_object=True,
            )
            return bool(out)
        except Exception:
            logger.exception("LLM warmup failed")
            return False

    def _resolve_system_prompt(self) -> str:
        return build_resolve_system_prompt()

    def resolve(self, user_content: str) -> dict[str, Any] | None:
        if not self._ensure_running():
            return None
        try:
            raw = chat_completion(
                self._port,
                [
                    {"role": "system", "content": self._resolve_system_prompt()},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=self._num_predict_resolve,
                temperature=self._temperature_resolve,
                json_object=True,
            )
            parsed = parse_resolve_json(raw or "")
            if not isinstance(parsed, dict):
                return None
            return self._normalize_parsed_intent(parsed, user_content)
        except Exception:
            logger.exception("LLM resolve failed for: %r", user_content[:120])
            return None

    def _normalize_parsed_intent(
        self, parsed: dict[str, Any], user_content: str
    ) -> dict[str, Any] | None:
        kind = str(parsed.get("type", "")).strip().lower()
        if kind == "open" and isinstance(parsed.get("app"), str) and parsed["app"].strip():
            return {"type": "open", "app": parsed["app"].strip()}
        if kind == "close" and isinstance(parsed.get("app"), str) and parsed["app"].strip():
            raw_force = parsed.get("force", False)
            if isinstance(raw_force, str):
                force_close = raw_force.strip().lower() in {"true", "1", "yes"}
            else:
                force_close = bool(raw_force)
            return {
                "type": "close",
                "app": parsed["app"].strip(),
                "force": force_close,
            }
        if kind == "shutdown":
            return {"type": "shutdown"}
        if kind == "chat":
            reply = parsed.get("reply")
            if isinstance(reply, str) and reply.strip():
                out = reply.strip()
                if contains_profanity(out.lower()):
                    return {"type": "chat", "reply": REFUSAL_REPLY}
                return {"type": "chat", "reply": out}
        if kind == "clarify":
            reply = parsed.get("reply")
            pending = parsed.get("pending")
            if isinstance(reply, str) and reply.strip():
                pend = str(pending).strip().lower() if pending else "volume"
                if pend not in VALID_CLARIFY_PENDING:
                    pend = "volume"
                cleaned = reply.strip()
                low = cleaned.lower()
                if any(bad in low for bad in BAD_CLARIFY_SUBSTRINGS):
                    if pend == "brightness":
                        cleaned = (
                            "Roughly how much brighter—a little, or about ten or twenty percent?"
                        )
                    else:
                        cleaned = (
                            "Roughly how much louder—say a percent like ten or twenty, "
                            "or say a little or a lot."
                        )
                return {"type": "clarify", "reply": cleaned, "pending": pend}
        if kind == "volume_relative":
            d = coerce_json_number(parsed.get("delta_percent"))
            if d is not None:
                return {"type": "volume_relative", "delta_percent": d}
        if kind == "volume_set":
            p = coerce_json_number(parsed.get("percent"))
            if p is not None:
                return {"type": "volume_set", "percent": max(0.0, min(100.0, p))}
        if kind == "volume_mute":
            return {"type": "volume_mute"}
        if kind == "volume_unmute":
            return {"type": "volume_unmute"}
        if kind == "volume_status":
            return {"type": "volume_status"}
        if kind == "battery_status":
            return {"type": "battery_status"}
        if kind == "brightness_relative":
            d = coerce_json_number(parsed.get("delta_percent"))
            if d is not None:
                return {"type": "brightness_relative", "delta_percent": d}
        if kind == "brightness_set":
            p = coerce_json_number(parsed.get("percent"))
            if p is not None:
                return {"type": "brightness_set", "percent": max(0.0, min(100.0, p))}
        if kind == "wifi":
            act = str(parsed.get("action", "toggle")).strip().lower()
            if act in {"toggle", "on", "off"}:
                return {"type": "wifi", "action": act}
        if kind == "hotspot":
            act = str(parsed.get("action", "toggle")).strip().lower()
            if act in {"toggle", "on", "off"}:
                return {"type": "hotspot", "action": act}
        if kind == "unknown":
            return {"type": "unknown", "raw": user_content}
        return None

    def generate_reply(self, text: str) -> str | None:
        if not self._ensure_running():
            return None
        system = build_chat_system_prompt()
        try:
            raw = chat_completion(
                self._port,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                max_tokens=self._num_predict_chat,
                temperature=0.25,
            )
            if not raw:
                return None
            reply = raw.strip().split("\n\n")[0].strip()
            if len(reply) < 2:
                return None
            return sanitize_reply_text(reply)
        except Exception:
            logger.exception("LLM chat generation failed for: %r", text[:120])
            return None

    def chat_reply(self, text: str) -> str | None:
        norm = " ".join(text.lower().strip().split())
        if contains_profanity(norm):
            return REFUSAL_REPLY
        return self.generate_reply(text)


# Backward-compatible alias
LlamaCppIntentBackend = GgufIntentBackend
