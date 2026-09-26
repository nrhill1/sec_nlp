# src/sec_nlp/core/infra/settings.py
"""Installed application storage paths and provider cache settings."""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_cache_dir, user_data_dir


class PathSecurityError(RuntimeError):
    """Raised when a path cannot be validated as safe."""


CACHE_DIR = Path(os.environ.get("SEC_NLP_CACHE_DIR", user_cache_dir("sec-nlp")))
DATA_DIR = Path(os.environ.get("SEC_NLP_DATA_DIR", user_data_dir("sec-nlp")))


def _read_int_setting(name: str, default: int) -> int:
    """Read integer setting from environment with fallback handling."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise PathSecurityError(
            f"Invalid integer for {name}: {raw_value}"
        ) from exc


def _read_float_setting(name: str, default: float) -> float:
    """Read float setting from environment with fallback handling."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise PathSecurityError(
            f"Invalid float for {name}: {raw_value}"
        ) from exc


MARKET_CACHE_TTL_SECONDS: float = _read_float_setting(
    "SEC_NLP_MARKET_CACHE_TTL_SECONDS",
    300.0,
)
MARKET_CACHE_MAX_ENTRIES: int = _read_int_setting(
    "SEC_NLP_MARKET_CACHE_MAX_ENTRIES",
    128,
)
MARKET_RETRY_ATTEMPTS: int = _read_int_setting(
    "SEC_NLP_MARKET_RETRY_ATTEMPTS",
    3,
)
MARKET_RETRY_BACKOFF_SECONDS: float = _read_float_setting(
    "SEC_NLP_MARKET_RETRY_BACKOFF_SECONDS",
    0.5,
)
MARKET_RETRY_BACKOFF_MULTIPLIER: float = _read_float_setting(
    "SEC_NLP_MARKET_RETRY_BACKOFF_MULTIPLIER",
    2.0,
)
