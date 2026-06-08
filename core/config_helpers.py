"""Read config values from DoraConfig or plain mappings."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.config import DoraConfig


def _mapping(config: DoraConfig | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(config, DoraConfig):
        return config.to_dict()
    return config


def config_get(config: DoraConfig | Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    data = _mapping(config)
    for key in keys:
        if key in data:
            return data[key]
    return default


def config_bool(
    config: DoraConfig | Mapping[str, Any], *keys: str, default: bool = False
) -> bool:
    return bool(config_get(config, *keys, default=default))


def config_int(
    config: DoraConfig | Mapping[str, Any], *keys: str, default: int = 0
) -> int:
    value = config_get(config, *keys, default=default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def config_float(
    config: DoraConfig | Mapping[str, Any], *keys: str, default: float = 0.0
) -> float:
    value = config_get(config, *keys, default=default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def config_optional_positive_int(
    config: DoraConfig | Mapping[str, Any], *keys: str
) -> int | None:
    raw = config_get(config, *keys)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None
