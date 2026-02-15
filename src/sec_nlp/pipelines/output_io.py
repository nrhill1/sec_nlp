# src/sec_nlp/pipelines/output_io.py
"""Shared output serialization helpers for pipeline exports."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO
from uuid import UUID

from pydantic import BaseModel

from sec_nlp.pipelines.serialization import serialize_payload
from sec_nlp.pipelines.utils import safe_filename
from sec_nlp.types import JsonValue


def format_accession(accession: str | None) -> str:
    """Return a filesystem-safe accession identifier."""
    return safe_filename((accession or "unknown").replace("-", "_"))


def build_accession_dir(output_dir: Path, accession: str | None) -> Path:
    """Create and return the per-accession output directory."""
    safe_acc = format_accession(accession)
    accession_dir = output_dir / safe_acc
    accession_dir.mkdir(parents=True, exist_ok=True)
    return accession_dir


def build_run_file_stem(
    symbol: str,
    suffix: str,
    run_id: UUID | None,
) -> str:
    """Build a filename stem with a run_id suffix when provided."""
    run_component = f"_{run_id}" if run_id is not None else ""
    return f"{symbol.lower()}_{suffix}{run_component}"


def build_accession_file_stem(
    symbol: str,
    suffix: str,
    accession: str | None,
    run_id: UUID | None,
) -> str:
    """Build a filename stem that includes the accession and run_id."""
    safe_acc = format_accession(accession)
    run_component = f"_{run_id}" if run_id is not None else ""
    return f"{symbol.lower()}_{suffix}_{safe_acc}{run_component}"


def build_run_header_fields(
    *,
    run_timestamp: datetime,
    run_id: UUID | str,
    run_short_id: int | None,
) -> dict[str, JsonValue]:
    """Build a standard run header payload for output files."""
    short_id = (
        run_short_id
        if isinstance(run_short_id, int) and run_short_id > 0
        else None
    )
    run_id_text = str(run_id)
    return {
        "run_timestamp": run_timestamp.astimezone(UTC).isoformat(),
        "run_short_id": short_id,
        "run_id": run_id_text,
        "run_short_id_display": f"#{short_id}"
        if short_id is not None
        else run_id_text,
    }


def write_csv_metadata_comments(
    handle: TextIO,
    header_fields: Mapping[str, JsonValue] | None = None,
) -> None:
    """Write metadata as commented CSV preamble lines.

    The emitted `# key: value` lines keep the tabular data unchanged while
    preserving run-level provenance in the file.
    """
    if not header_fields:
        return
    for key, value in header_fields.items():
        if value is None:
            rendered = ""
        else:
            rendered = str(value)
        handle.write(f"# {key}: {rendered}\n")


def write_json(
    path: Path,
    data: JsonValue | BaseModel,
    *,
    payload: JsonValue | None = None,
    indent: int = 2,
    ensure_ascii: bool = True,
    exclude_none: bool = False,
) -> None:
    """Write JSON data to disk."""
    if payload is None:
        payload = serialize_payload(data, exclude_none=exclude_none)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=indent, ensure_ascii=ensure_ascii)


def write_yaml(
    path: Path,
    data: JsonValue | BaseModel,
    *,
    payload: JsonValue | None = None,
    sort_keys: bool = False,
    allow_unicode: bool | None = None,
    exclude_none: bool = False,
) -> None:
    """Write YAML data to disk."""
    import yaml

    if payload is None:
        payload = serialize_payload(data, exclude_none=exclude_none)

    with open(path, "w", encoding="utf-8") as f:
        if allow_unicode is None:
            yaml.safe_dump(payload, f, sort_keys=sort_keys)
        else:
            yaml.safe_dump(
                payload, f, sort_keys=sort_keys, allow_unicode=allow_unicode
            )
