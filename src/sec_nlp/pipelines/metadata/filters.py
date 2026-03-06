# src/sec_nlp/pipelines/metadata/filters.py
"""Metadata filter helpers for vector search."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

type MetadataFilterValue = str | int | bool
type MetadataFilterInput = MetadataFilterValue | Sequence[MetadataFilterValue]
type MetadataFilters = Mapping[str, MetadataFilterInput]

# QdrantVectorStore nests document metadata under a "metadata" payload key.
# Filter field paths must use this prefix to match the stored payload structure.
_QDRANT_METADATA_PREFIX = "metadata"


def _prefixed_key(key: str) -> str:
    """Prefix a metadata key for the Qdrant payload path.

    QdrantVectorStore stores document metadata under a ``metadata`` key in the
    Qdrant point payload (e.g. ``{"page_content": ..., "metadata": {...}}``),
    so filter field conditions must use ``metadata.<key>`` to match.
    """
    if key.startswith(f"{_QDRANT_METADATA_PREFIX}."):
        return key
    return f"{_QDRANT_METADATA_PREFIX}.{key}"


def build_metadata_filter(raw_filters: MetadataFilters) -> Filter | None:
    """Construct a Qdrant metadata filter from config-style mappings."""
    conditions: list[FieldCondition] = []

    for key, raw_value in raw_filters.items():
        values = _normalize_filter_values(raw_value)
        cleaned = [v for v in values if v != ""]
        if not cleaned:
            continue

        field_key = _prefixed_key(key)

        if len(cleaned) == 1:
            conditions.append(
                FieldCondition(
                    key=field_key, match=MatchValue(value=cleaned[0])
                )
            )
            continue

        str_values: list[str] = []
        int_values: list[int] = []
        bool_values: list[bool] = []
        for value in cleaned:
            if isinstance(value, str):
                str_values.append(value)
            elif isinstance(value, bool):
                bool_values.append(value)
            else:
                int_values.append(value)

        if len(str_values) == len(cleaned):
            conditions.append(
                FieldCondition(key=field_key, match=MatchAny(any=str_values))
            )
            continue

        if len(int_values) == len(cleaned):
            conditions.append(
                FieldCondition(key=field_key, match=MatchAny(any=int_values))
            )
            continue

        if len(bool_values) == len(cleaned):
            unique_bools = list(dict.fromkeys(bool_values))
            if len(unique_bools) == 1:
                conditions.append(
                    FieldCondition(
                        key=field_key,
                        match=MatchValue(value=unique_bools[0]),
                    )
                )
            continue

        coerced_values = [str(v) for v in cleaned]
        conditions.append(
            FieldCondition(key=field_key, match=MatchAny(any=coerced_values))
        )

    if not conditions:
        return None

    return Filter(must=list(conditions))


def _normalize_filter_values(
    raw_value: MetadataFilterInput,
) -> list[MetadataFilterValue]:
    """Normalize scalar or sequence filter values into a concrete list."""
    if isinstance(raw_value, (str, bool, int)):
        return [raw_value]
    return list(raw_value)
