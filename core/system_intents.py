"""Intent types handled by core.system_actions.apply_system_intent."""

from __future__ import annotations

SYSTEM_INTENT_TYPES: frozenset[str] = frozenset(
    {
        "volume_relative",
        "volume_set",
        "volume_mute",
        "volume_unmute",
        "brightness_relative",
        "brightness_set",
        "wifi",
        "hotspot",
        "battery_status",
        "volume_status",
    }
)


def is_system_intent(intent_type: str | None) -> bool:
    return intent_type in SYSTEM_INTENT_TYPES
