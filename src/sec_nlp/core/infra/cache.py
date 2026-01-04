# src/sec_nlp/core/cache.py
"""Simple file-based caching utilities using the OS user cache directory.

This module centralizes cache directory resolution and TTL checks.

Usage:
    from sec_nlp.core.infra.cache import get_cache_dir, is_fresh, read_json, write_json, sha256_hex

    # Get a cache directory (creates if needed)
    cache_dir = get_cache_dir("my_pipeline", "subdir")

    # Create a cache key from inputs
    key = sha256_hex(json.dumps({"symbol": "AAPL", "period": "2024"}))
    cache_file = cache_dir / f"{key}.json"

    # Check if cached result is fresh (within TTL)
    if is_fresh(cache_file, ttl_seconds=3600 * 24):  # 24 hours
        data = read_json(cache_file)
    else:
        data = expensive_computation()
        write_json(cache_file, data)
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from pydantic.dataclasses import dataclass

from sec_nlp.core.infra.settings import PROJECT_ROOT
from sec_nlp.types import JsonValue

# Type alias for JSON-serializable data
JSONData = JsonValue


def _ensure_dir(path: Path) -> Path:
    """Create a directory tree and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


# Keep cache under the project root to avoid user-level surprises
APP_CACHE_DIR: Path = PROJECT_ROOT / ".cache"


def get_cache_dir(*subdirs: str) -> Path:
    """Return a cache directory path and ensure it exists."""
    d: Path = APP_CACHE_DIR.joinpath(*subdirs)
    d.mkdir(parents=True, exist_ok=True)
    return d


def sha256_hex(payload: str | bytes) -> str:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def is_fresh(path: Path, ttl_seconds: int) -> bool:
    if not path.exists():
        return False
    try:
        mtime: int | float = path.stat().st_mtime
    except OSError:
        return False
    return (time.time() - mtime) <= ttl_seconds


@dataclass(frozen=True)
class CacheEntry:
    path: Path
    fresh: bool


def read_json(path: Path) -> JSONData:
    with open(path, encoding="utf-8") as f:
        data: JSONData = json.load(f)
        return data


def write_json(path: Path, data: JSONData) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)
