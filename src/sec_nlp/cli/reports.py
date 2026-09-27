# src/sec_nlp/cli/reports.py
"""Read explicitly selected research artifacts as structured terminal text.

Analyze, exhibit, warranty, and deterministic specialist outputs retain their
own schemas. This viewer separates interpretation from source evidence within
each record and reads only the local file requested by the user.
"""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import yaml
from pydantic import TypeAdapter, ValidationError
from rich.console import Console
from rich.text import Text

from sec_nlp.cli.evidence import _fields, _heading, _label, _value_text
from sec_nlp.core.types import is_json_array, is_json_object
from sec_nlp.types import JsonValue

_MAX_BYTES = 10 * 1024 * 1024
_EVIDENCE = frozenset(
    {
        "evidence",
        "evidence_spans",
        "sources",
        "source",
        "source_url",
        "source_links",
        "citations",
        "quote",
        "quotes",
        "excerpt",
        "excerpts",
        "chunk",
        "chunk_text",
        "raw_chunk",
        "chunk_preview",
        "source_excerpt",
        "source_metadata",
        "text",
        "filing_url",
        "document_url",
        "filenames",
        "document_metadata",
        "metadata",
        "provenance",
        "filing",
    }
)
_PROVENANCE = frozenset(
    {
        "symbol",
        "symbols",
        "filing",
        "form_type",
        "search_queries",
        "provenance",
        "schema_version",
        "generated_at",
        "run_id",
    }
)


def _is_evidence(name: str) -> bool:
    """Recognize source fields without importing specialist result models."""
    return name in _EVIDENCE or name.endswith(("_sources", "_source_url"))


def _show_mapping(console: Console, value: Mapping[str, JsonValue]) -> None:
    """Keep nested evidence attached to its containing finding or filing.

    Args:
        console: Terminal destination for the current record.
        value: Validated report mapping to display without dropping fields.
    """
    details = [
        (name, item) for name, item in value.items() if not _is_evidence(name)
    ]
    evidence = [
        (name, item) for name, item in value.items() if _is_evidence(name)
    ]
    scalar = [
        (name, item)
        for name, item in details
        if not isinstance(item, Mapping)
        and not (isinstance(item, Sequence) and not isinstance(item, str))
    ]
    nested = [
        (name, item)
        for name, item in details
        if isinstance(item, Mapping)
        or (isinstance(item, Sequence) and not isinstance(item, str))
    ]
    if scalar:
        _fields(
            console,
            tuple((_label(name), _value_text(item)) for name, item in scalar),
        )
    for name, item in nested:
        console.print(Text(_label(name), style="bold"))
        _show_value(console, item)
    if evidence:
        console.print(Text("Evidence and source provenance", style="bold cyan"))
        _fields(
            console,
            tuple((_label(name), _value_text(item)) for name, item in evidence),
        )
    if not value:
        console.print(Text("No values supplied."))


def _show_value(console: Console, value: JsonValue) -> None:
    """Render nested records with visible boundaries and literal text."""
    if is_json_object(value):
        _show_mapping(console, value)
    elif is_json_array(value):
        if not value:
            console.print(Text("None."))
        for number, item in enumerate(value, start=1):
            if is_json_object(item) or is_json_array(item):
                console.print(Text(f"Record {number}", style="bold"))
                _show_value(console, item)
            else:
                console.print(
                    Text(f"{number}. {_value_text(item)}"), soft_wrap=True
                )
    else:
        console.print(Text(_value_text(value)), soft_wrap=True)


def _read_report(path: Path) -> JsonValue:
    """Read one bounded JSON or safely loaded YAML artifact.

    Args:
        path: Explicitly selected regular local report file.

    Returns:
        Validated JSON-compatible report data.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If its type, size, or structured contents are unsupported.
    """
    if path.suffix.lower() not in {".json", ".yaml", ".yml"}:
        raise ValueError("Research reports must be JSON or YAML files.")
    if not path.is_file():
        raise ValueError(f"Research report is not a regular file: {path}")
    with path.open("rb") as source:
        raw = source.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise ValueError("Research report exceeds the 10 MiB display limit.")
    try:
        text = raw.decode("utf-8-sig")
        adapter = TypeAdapter(JsonValue)
        if path.suffix.lower() == ".json":
            return adapter.validate_json(text)
        return adapter.validate_python(yaml.safe_load(text))
    except (
        UnicodeError,
        yaml.YAMLError,
        ValidationError,
        RecursionError,
    ) as exc:
        raise ValueError(
            f"Research report is not valid JSON-compatible {path.suffix[1:].upper()}: {exc}"
        ) from exc


def show_report(
    path: Path, *, as_json: bool = False, console: Console | None = None
) -> None:
    """Display an explicitly selected report without running research or models.

    Args:
        path: Existing local JSON or YAML specialist artifact to view.
        as_json: Whether to return the decoded payload as structured JSON.
        console: Optional terminal output destination for embedding or tests.

    Raises:
        OSError: If the artifact cannot be read.
        ValueError: If its type, size, or structured contents are unsupported.
    """
    payload = _read_report(path)
    output = console or Console()
    if as_json:
        output.print_json(json=json.dumps(payload, ensure_ascii=False))
        return
    _heading(output, "Research report")
    output.print(Text(f"Local artifact: {path}"), soft_wrap=True)
    if is_json_object(payload):
        provenance = {
            name: item for name, item in payload.items() if name in _PROVENANCE
        }
        if provenance:
            _heading(output, "Report provenance")
            _fields(
                output,
                tuple(
                    (_label(name), _value_text(item))
                    for name, item in provenance.items()
                ),
            )
        _heading(output, "Findings and interpretation")
        _show_mapping(
            output,
            {
                name: item
                for name, item in payload.items()
                if name not in _PROVENANCE
            },
        )
    else:
        _heading(output, "Findings and interpretation")
        _show_value(output, payload)
