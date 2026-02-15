from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import TextIO
from uuid import UUID

from pydantic import BaseModel

from sec_nlp.pipelines.utils import safe_filename as safe_filename
from sec_nlp.types import JsonValue as JsonValue

def format_accession(accession: str | None) -> str: ...
def build_accession_dir(output_dir: Path, accession: str | None) -> Path: ...
def build_run_file_stem(
    symbol: str, suffix: str, run_id: int | str | None
) -> str: ...
def build_accession_file_stem(
    symbol: str, suffix: str, accession: str | None, run_id: int | str | None
) -> str: ...
def build_run_header_fields(
    *, run_timestamp: datetime, run_id: UUID | str, run_short_id: int | None
) -> dict[str, JsonValue]: ...
def write_csv_metadata_comments(
    handle: TextIO, header_fields: Mapping[str, JsonValue] | None = None
) -> None: ...
def write_json(
    path: Path,
    data: JsonValue | BaseModel,
    *,
    indent: int = 2,
    ensure_ascii: bool = True,
    exclude_none: bool = False,
) -> None: ...
def write_yaml(
    path: Path,
    data: JsonValue | BaseModel,
    *,
    sort_keys: bool = False,
    allow_unicode: bool | None = None,
    exclude_none: bool = False,
) -> None: ...
