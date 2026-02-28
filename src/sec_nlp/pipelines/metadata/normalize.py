# src/sec_nlp/pipelines/metadata/normalize.py
"""Shared helpers for normalizing metadata values."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from sec_nlp.pipelines.serialization import is_score_key, round_score
from sec_nlp.pipelines.types import MetadataMap, MetadataValue
from sec_nlp.types import JsonDict, JsonValue


def coerce_meta_str(value: MetadataValue) -> str | None:
    """Normalize metadata scalars to string values."""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return None


def get_meta_str(meta: MetadataMap, key: str) -> str | None:
    """Read a metadata key as a normalized string."""
    value = meta.get(key)
    if value is None:
        return None
    return coerce_meta_str(value)


def get_meta_str_any(
    meta: MetadataMap,
    keys: Iterable[str],
    *,
    include_source_meta: bool = True,
) -> str | None:
    """Return the first matching metadata value across candidate keys."""
    for key in keys:
        value = meta.get(key)
        if value is None:
            continue
        coerced = coerce_meta_str(value)
        if coerced is not None:
            return coerced
    if include_source_meta:
        source_meta = meta.get("source_metadata")
        if isinstance(source_meta, dict):
            for key in keys:
                value = source_meta.get(key)
                if value is None:
                    continue
                coerced = coerce_meta_str(value)
                if coerced is not None:
                    return coerced
    return None


_OMIT_METADATA_KEYS: set[str] = {
    "raw_chunk",
    "page_content",
}


def normalize_metadata_for_output(
    metadata: MetadataMap | None,
) -> JsonDict:
    """Convert internal metadata to a stable JSON output payload."""
    if not metadata:
        return {}
    payload: JsonDict = {}
    for key, raw_value in metadata.items():
        if not isinstance(key, str):
            continue
        if key in _OMIT_METADATA_KEYS:
            continue
        normalized = _normalize_metadata_value(key, raw_value)
        if normalized is not None:
            payload[key] = normalized
    return payload


def _normalize_metadata_value(
    key: str, value: MetadataValue | Path
) -> JsonValue | None:
    """Normalize metadata value."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (int, float)) and is_score_key(key):
        return round_score(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        nested: JsonDict = {}
        for nested_key, nested_value in value.items():
            if not isinstance(nested_key, str):
                continue
            if nested_key in _OMIT_METADATA_KEYS:
                continue
            normalized = _normalize_metadata_value(nested_key, nested_value)
            if normalized is not None:
                nested[nested_key] = normalized
        return nested or None
    if isinstance(value, list):
        items: list[JsonValue] = []
        for item in value:
            normalized = _normalize_metadata_value(key, item)
            if normalized is not None:
                items.append(normalized)
        return items or None
    return None
