"""Backward-compatible re-export — prefer ``core.assistant`` for new code."""

from core.assistant import DoraAssistant, run_assistant

__all__ = ["DoraAssistant", "run_assistant"]
