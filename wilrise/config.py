"""Optional config helpers: build Wilrise options from environment variables."""

import logging
import os
from typing import TypedDict


class WilriseEnvConfig(TypedDict, total=False):
    """Optional keys that from_env() may include."""

    log_level: int


class WilriseEnvConfigRequired(WilriseEnvConfig):
    """Return type of from_env(). Pass to Wilrise(**from_env()) for env-based config."""

    debug: bool
    max_batch_size: int
    max_request_size: int
    log_requests: bool


def from_env() -> WilriseEnvConfigRequired:
    """Build Wilrise init kwargs from env. Keys match __init__; unset -> defaults.

    WILRISE_LOG_LEVEL: DEBUG|INFO|WARNING|ERROR (case-insensitive).
    """

    def _bool(key: str, default: bool) -> bool:
        v = os.environ.get(key)
        if v is None:
            return default
        return v.strip().lower() in ("1", "true", "yes")

    def _log_level(key: str) -> int | None:
        v = os.environ.get(key)
        if v is None or not v.strip():
            return None
        name = v.strip().upper()
        level = getattr(logging, name, None)
        if isinstance(level, int):
            return level
        return None

    out: WilriseEnvConfigRequired = {
        "debug": _bool("WILRISE_DEBUG", False),
        "max_batch_size": int(os.environ.get("WILRISE_MAX_BATCH_SIZE", "50")),
        "max_request_size": int(os.environ.get("WILRISE_MAX_REQUEST_SIZE", "1048576")),
        "log_requests": _bool("WILRISE_LOG_REQUESTS", True),
    }
    log_level = _log_level("WILRISE_LOG_LEVEL")
    if log_level is not None:
        out["log_level"] = log_level
    return out
