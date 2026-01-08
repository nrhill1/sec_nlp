from pathlib import Path

from sec_nlp.core.infra.settings import PROJECT_ROOT as PROJECT_ROOT
from sec_nlp.types import JsonValue as JsonValue

JSONData = JsonValue
APP_CACHE_DIR: Path

def get_cache_dir(*subdirs: str) -> Path: ...
def sha256_hex(payload: str | bytes) -> str: ...
def is_fresh(path: Path, ttl_seconds: int) -> bool: ...

class CacheEntry:
    path: Path
    fresh: bool

def read_json(path: Path) -> JSONData: ...
def write_json(path: Path, data: JSONData) -> None: ...
