"""Read config values with legacy key fallbacks."""

from __future__ import annotations

from typing import Any


def config_get(config: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in config:
            return config[key]
    return default


def config_bool(config: dict[str, Any], *keys: str, default: bool = False) -> bool:
    value = config_get(config, *keys, default=default)
    return bool(value)


def config_int(config: dict[str, Any], *keys: str, default: int = 0) -> int:
    value = config_get(config, *keys, default=default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def config_float(config: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    value = config_get(config, *keys, default=default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def config_optional_positive_int(config: dict[str, Any], *keys: str) -> int | None:
    raw = config_get(config, *keys)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None
