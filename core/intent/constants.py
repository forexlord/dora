"""Shared vocabulary and tuning for intent handling."""

from __future__ import annotations

OPEN_WORDS = frozenset(
    {"open", "ouvre", "abrir", "apri", "launch", "start", "run", "load"}
)
CLOSE_WORDS = frozenset({"close", "ferme", "fermer", "cerrar", "chiudi"})
# Phrases that mean kill the process (confirmation + /F), not a normal window close.
FORCE_CLOSE_WORDS = frozenset(
    {"force close", "force quit", "hard close", "force kill"}
)
SHUTDOWN_WORDS = frozenset(
    {"shutdown", "shut down", "eteindre", "arrêter", "arreter", "apagar"}
)
CONFIRM_WORDS = frozenset({"yes", "y", "oui", "si"})
SHELL_LIKE_WORDS = frozenset({"clear", "cls", "exit", "quit", "help"})

DEFAULT_VOLUME_STEP_PERCENT = 10.0
DEFAULT_BRIGHTNESS_STEP_PERCENT = 10.0

REFUSAL_REPLY = "I can't help with that."

DORA_CREATOR_REPLY = (
    "I was created by Recovery Eyo, a software engineer from Nigeria. "
    "You can look him up online."
)

DORA_CREATOR_MORE_REPLY = (
    "Recovery Eyo is a software engineer from Nigeria. He built Dora as a local "
    "Windows voice assistant. You can search for Recovery Eyo online to learn more."
)

DORA_NAME_REPLY = "My name is Dora. I'm a Windows voice assistant on your PC."

# Substrings in model-generated clarify prompts we replace with useful questions.
BAD_CLARIFY_SUBSTRINGS: tuple[str, ...] = (
    "current volume",
    "current brightness",
    "what is the volume",
    "what's the volume",
    "what is your volume",
    "what's your volume",
    "your volume level",
    "how loud is it",
    "what level is",
    "do you know the volume",
)

VALID_CLARIFY_PENDING = frozenset({"volume", "brightness", "wifi", "hotspot"})
