"""Shared output serialization helpers for pipeline exports."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

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
    run_id: int | str | None,
) -> str:
    """Build a filename stem with a run_id suffix when provided."""
    run_component = f"_{run_id}" if run_id is not None else ""
    return f"{symbol.lower()}_{suffix}{run_component}"


def build_accession_file_stem(
    symbol: str,
    suffix: str,
    accession: str | None,
    run_id: int | str | None,
) -> str:
    """Build a filename stem that includes the accession and run_id."""
    safe_acc = format_accession(accession)
    run_component = f"_{run_id}" if run_id is not None else ""
    return f"{symbol.lower()}_{suffix}_{safe_acc}{run_component}"


def write_json(
    path: Path,
    data: JsonValue | BaseModel,
    *,
    indent: int = 2,
    ensure_ascii: bool = True,
    exclude_none: bool = False,
) -> None:
    """Write JSON data to disk."""
    payload = (
        data.model_dump(mode="json", exclude_none=exclude_none)
        if isinstance(data, BaseModel)
        else data
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=indent, ensure_ascii=ensure_ascii)


def write_yaml(
    path: Path,
    data: JsonValue | BaseModel,
    *,
    sort_keys: bool = False,
    allow_unicode: bool | None = None,
    exclude_none: bool = False,
) -> None:
    """Write YAML data to disk."""
    import yaml

    payload = (
        data.model_dump(mode="json", exclude_none=exclude_none)
        if isinstance(data, BaseModel)
        else data
    )

    with open(path, "w", encoding="utf-8") as f:
        if allow_unicode is None:
            yaml.safe_dump(payload, f, sort_keys=sort_keys)
        else:
            yaml.safe_dump(
                payload, f, sort_keys=sort_keys, allow_unicode=allow_unicode
            )
