"""Terminal output with real Rich colors (no raw [cyan] markup in the console)."""

from __future__ import annotations

from rich.console import Console

_console = Console(legacy_windows=False)
_verbose_voice = False


def configure(*, verbose_voice: bool) -> None:
    """When False (overlay on), skip mic/wake/thinking transcript lines in the terminal."""
    global _verbose_voice
    _verbose_voice = verbose_voice


def emit_markup(text: str) -> None:
    _console.print(text, markup=True)


def emit(text: str, *, style: str | None = None) -> None:
    _console.print(text, style=style)


def emit_reply(text: str) -> None:
    _console.print(text, style="magenta")


def emit_result(text: str, *, style: str) -> None:
    _console.print(text, style=style)


def emit_voice(text: str, *, style: str = "cyan") -> None:
    if not _verbose_voice:
        return
    _console.print(text, style=style)


def emit_dim(text: str) -> None:
    if not _verbose_voice:
        return
    _console.print(text, style="dim")


def emit_heard(text: str) -> None:
    if not _verbose_voice:
        return
    _console.print(f"Heard: {text}", style="cyan")


def emit_wake_detected() -> None:
    if not _verbose_voice:
        return
    _console.print("Wake word detected. Listening for command...", style="cyan")


def emit_thinking() -> None:
    if not _verbose_voice:
        return
    _console.print("Thinking…", style="dim")


def emit_listen_prompt() -> None:
    if not _verbose_voice:
        return
    _console.print("Listening... speak now.", style="cyan")
