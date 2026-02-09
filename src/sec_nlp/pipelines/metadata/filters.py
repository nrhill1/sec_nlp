# src/sec_nlp/pipelines/metadata/filters.py
"""Metadata filter helpers for vector search."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

type MetadataFilterValue = str | int | bool
type MetadataFilters = Mapping[str, Sequence[MetadataFilterValue]]

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
        values: list[MetadataFilterValue]
        if isinstance(raw_value, str):
            values = [raw_value]
        else:
            values = list(raw_value)
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

        str_values = [v for v in cleaned if isinstance(v, str)]
        int_values = [
            v for v in cleaned if isinstance(v, int) and not isinstance(v, bool)
        ]
        bool_values = [v for v in cleaned if isinstance(v, bool)]

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
            conditions.append(
                FieldCondition(key=field_key, match=MatchAny(any=bool_values))
            )
            continue

        coerced_values = [str(v) for v in cleaned]
        conditions.append(
            FieldCondition(key=field_key, match=MatchAny(any=coerced_values))
        )

    if not conditions:
        return None

    return Filter(must=list(conditions))
