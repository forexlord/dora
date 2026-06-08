"""Typed contract shared by DoraAssistant and its mixins."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from core.config import DoraConfig
    from core.executor import CommandExecutor
    from core.intent import IntentParser
    from core.listener import VoiceListener, WhisperVoiceListener
    from core.permissions import PermissionStore
    from core.session import SessionState
    from core.status_overlay import StatusOverlay
    from core.tts import TextToSpeech


class AssistantHost(Protocol):
    """Attributes and hooks mixins may rely on."""

    _config: DoraConfig
    _permission_store: PermissionStore
    _parser: IntentParser
    _tts: TextToSpeech
    _executor: CommandExecutor
    _listener: VoiceListener | WhisperVoiceListener | None
    _wake_word_enabled: bool
    _wake_phrases: list[str]
    _wake_hint: str
    _wake_prefix_alts: frozenset[str]
    _voice_session_after_wake_sec: int
    _voice_processing_grace_sec: int
    _post_response_listen_window_sec: int
    _voice_idle_timeout_sec: float
    _text_fallback_enabled: bool
    _warmup_llm_on_start: bool
    _llm_ready: bool
    _idle_rms_threshold: float
    _echo_listen_status: bool
    _show_processing_on_speech_pause: bool
    _speech_pause_to_processing_sec: float
    _startup_complete: bool
    _overlay_user_hidden: bool
    _user_cancelled: bool
    _cancel_event: threading.Event
    _session: SessionState | None
    _overlay: StatusOverlay
    _use_llm: bool
    _allow_chat_fallback: bool

    def _set_overlay_phase(self, phase: str, detail: str = "") -> None: ...
    def _overlay_before_listen(self, state: SessionState) -> None: ...
    def _overlay_hidden_until_wake(self) -> bool: ...
    def _refresh_overlay_post_start(self, state: SessionState) -> None: ...
    def _announce_ready(self, begin_overlay_hidden: bool) -> None: ...
    def _dispatch_turn(self, text: str, state: SessionState) -> None: ...
    def _normalize_wake_hearing(self, normalized: str) -> str: ...
