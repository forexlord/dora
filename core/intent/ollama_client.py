"""Ollama chat/generate integration for JSON intent resolution and free-form replies."""

from __future__ import annotations

import json
import re
from typing import Any

try:
    import ollama
except ImportError:  # pragma: no cover
    ollama = None

from .constants import (
    BAD_CLARIFY_SUBSTRINGS,
    DEFAULT_BRIGHTNESS_STEP_PERCENT,
    DEFAULT_VOLUME_STEP_PERCENT,
    DORA_CREATOR_REPLY,
    REFUSAL_REPLY,
    VALID_CLARIFY_PENDING,
)
from .safety import contains_profanity, sanitize_reply_text


def message_content(response: Any) -> str:
    if isinstance(response, dict):
        msg = response.get("message")
    else:
        msg = response.message
    if isinstance(msg, dict):
        raw = msg.get("content", "")
    else:
        raw = getattr(msg, "content", "") or ""
    return (raw or "").strip()


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


class OllamaIntentBackend:
    """Calls local Ollama for structured intents (JSON) and conversational fallbacks."""

    def __init__(
        self,
        model: str = "phi",
        *,
        chat_model: str | None = None,
        num_predict_resolve: int = 120,
        num_predict_chat: int = 128,
        temperature_resolve: float = 0.0,
        num_ctx: int | None = None,
    ) -> None:
        self.model = model.strip() or "phi"
        chat = (chat_model or "").strip()
        self._chat_model = chat if chat and chat != self.model else self.model
        self._num_predict_resolve = max(24, int(num_predict_resolve))
        self._num_predict_chat = max(32, min(int(num_predict_chat), 160))
        self._temperature_resolve = float(temperature_resolve)
        self._num_ctx = int(num_ctx) if num_ctx is not None else None

    def _runtime_options(
        self, *, num_predict: int, temperature: float
    ) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "temperature": temperature,
            "num_predict": int(num_predict),
        }
        if self._num_ctx is not None:
            opts["num_ctx"] = self._num_ctx
        return opts

    def available(self) -> bool:
        return ollama is not None

    def warmup(self) -> bool:
        if ollama is None:
            return False
        ok = False
        try:
            ollama.generate(
                model=self._chat_model,
                prompt="User: ping\nDora: ok",
                keep_alive="30m",
                options=self._runtime_options(num_predict=8, temperature=0.0),
            )
            ok = True
        except Exception:
            pass
        if self._chat_model != self.model:
            try:
                ollama.chat(
                    model=self.model,
                    format="json",
                    keep_alive="30m",
                    messages=[
                        {
                            "role": "system",
                            "content": 'Reply JSON only: {"type":"chat","reply":"ok"}',
                        },
                        {"role": "user", "content": "ping"},
                    ],
                    options=self._runtime_options(num_predict=16, temperature=0.0),
                )
                ok = True
            except Exception:
                pass
        elif not ok:
            try:
                ollama.chat(
                    model=self.model,
                    format="json",
                    keep_alive="30m",
                    messages=[
                        {
                            "role": "system",
                            "content": 'Reply JSON only: {"type":"chat","reply":"ok"}',
                        },
                        {"role": "user", "content": "ping"},
                    ],
                    options=self._runtime_options(num_predict=16, temperature=0.0),
                )
                ok = True
            except Exception:
                pass
        return ok

    def _resolve_system_prompt(self) -> str:
        step_v = int(DEFAULT_VOLUME_STEP_PERCENT)
        step_b = int(DEFAULT_BRIGHTNESS_STEP_PERCENT)
        return (
            "You are Dora, a Windows voice assistant created by Recovery Eyo "
            "(software engineer, Nigeria). Never say Microsoft, OpenAI, or another "
            f"company created you; for creator questions use: {DORA_CREATOR_REPLY}\n"
            "Input is speech-to-text: often incomplete or wrong.\n"
            "To report current volume or battery, use volume_status or battery_status "
            "types — never invent a number.\n"
            "If the message includes 'Context:' you are resolving a FOLLOW-UP; parse into system JSON.\n"
            "IMPORTANT: The computer already measures volume and screen brightness in software. "
            "NEVER ask the user what the current volume or brightness level is—they cannot see that number. "
            "NEVER ask 'what is your current volume' or similar.\n"
            "Decide ONE intent. Output a single JSON object only; keep it compact.\n"
            "Casual check-ins (e.g. are you there, how are you, can you hear me, what are you doing): "
            '{"type":"chat","reply":"<one short sentence>"} — never use unknown for those.\n'
            'open app: {"type":"open","app":"<name>"}\n'
            'close app normally (like clicking X, no confirmation): '
            '{"type":"close","app":"<name>","force":false}\n'
            'force kill only if user said force close/quit/kill or hard close: '
            '{"type":"close","app":"<name>","force":true}\n'
            'shutdown PC: {"type":"shutdown"}\n'
            'volume step (percentage POINTS from current, e.g. +20 means 50% goes to 70%): '
            '{"type":"volume_relative","delta_percent": <number>}\n'
            f'If user wants LOUDER or INCREASE volume but gives NO number (e.g. "turn it up", "increase volume", '
            f'"i want louder"), use {{"type":"volume_relative","delta_percent": {step_v}}} — do NOT use clarify.\n'
            f'If QUIETER with no number: {{"type":"volume_relative","delta_percent": -{step_v}}}.\n'
            'volume absolute 0-100: {"type":"volume_set","percent": <number>}\n'
            '{"type":"volume_mute"}  {"type":"volume_unmute"}\n'
            '{"type":"volume_status"} — user asks current volume level or if muted\n'
            '{"type":"battery_status"} — user asks battery percentage or charging\n'
            f"brightness: same rules; default brighter/dimmer without a number: +{step_b} or -{step_b} "
            "via brightness_relative.\n"
            'brightness_set / volume_set when they give an explicit percent.\n'
            'wifi: {"type":"wifi","action":"toggle"|"on"|"off"}\n'
            'hotspot: {"type":"hotspot","action":"toggle"|"on"|"off"}\n'
            'clarify ONLY if you truly need a number they did not give AND a default step is wrong—e.g. they said '
            '"change volume" without up or down. reply must ask HOW MUCH to change, e.g. "Roughly what percent '
            'louder—ten, twenty, or thirty?" Never ask for current level.\n'
            'pending for clarify: volume | brightness | wifi | hotspot\n'
            'Math (including spoken numbers, multiply/plus/etc.): '
            '{"type":"chat","reply":"<give the correct numeric result in one short sentence>"}\n'
            'Definitions and general knowledge (physics, antimatter, "what does X mean", explain) '
            'without needing live internet: {"type":"chat","reply":"<2-4 short clear sentences>"}\n'
            'Small talk / thanks / hello: {"type":"chat","reply":"<1-2 short sentences>"}\n'
            "If the user uses slurs, sexual content, hate, asks for illegal or dangerous how-to, "
            "self-harm instructions, malware, or personalized medical/legal diagnosis: "
            '{"type":"chat","reply":"I can\'t help with that."} (exactly that reply text)\n'
            'If nothing fits: {"type":"unknown"}\n'
            "Lowercase type and action. delta_percent negative means quieter/dimmer."
        )

    def resolve(self, user_content: str) -> dict[str, Any] | None:
        if ollama is None:
            return None
        try:
            response = ollama.chat(
                model=self.model,
                format="json",
                keep_alive="30m",
                messages=[
                    {"role": "system", "content": self._resolve_system_prompt()},
                    {"role": "user", "content": user_content},
                ],
                options=self._runtime_options(
                    num_predict=self._num_predict_resolve,
                    temperature=self._temperature_resolve,
                ),
            )
            parsed = parse_resolve_json(message_content(response))
            if not isinstance(parsed, dict):
                return None
            return self._normalize_parsed_intent(parsed, user_content)
        except Exception:
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
        """Fast spoken reply (``ollama generate`` — same style as ``ollama run`` in PowerShell)."""
        if ollama is None:
            return None
        block = (
            "You are Dora, a friendly Windows voice assistant created by Recovery Eyo, "
            "a software engineer from Nigeria (never say Microsoft or another company "
            f"made you; creator fact: {DORA_CREATOR_REPLY}). "
            "Reply in 1-3 short spoken sentences. Be warm and direct.\n"
            "Do not invent PC volume, battery, or brightness numbers — the app reads those separately.\n"
            "Math: state the correct number. Other facts: brief and accurate.\n"
            "Refuse only serious harm (illegal acts, self-harm, hate, explicit sexual content) "
            "with exactly: I can't help with that.\n"
            f"User: {text}\nDora:"
        )
        try:
            out = ollama.generate(
                model=self._chat_model,
                prompt=block,
                keep_alive="30m",
                options=self._runtime_options(
                    num_predict=self._num_predict_chat,
                    temperature=0.25,
                ),
            )
            raw = getattr(out, "response", None) or (
                out.get("response", "") if isinstance(out, dict) else ""
            )
            raw = raw or ""
            reply = raw.strip().split("\n\n")[0].strip()
            if len(reply) < 2:
                return None
            return sanitize_reply_text(reply)
        except Exception:
            return None

    def chat_reply(self, text: str) -> str | None:
        if ollama is None:
            return None
        norm = " ".join(text.lower().strip().split())
        if contains_profanity(norm):
            return REFUSAL_REPLY
        return self.generate_reply(text)
