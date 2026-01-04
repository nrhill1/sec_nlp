# src/sec_nlp/pipelines/vector/query.py
"""Shared Qdrant query helpers for pipelines."""

from __future__ import annotations

from qdrant_client import QdrantClient

from sec_nlp.pipelines.metadata.filters import (
    MetadataFilters,
    build_metadata_filter,
)


def scroll_exists(
    client: QdrantClient,
    collection_name: str,
    filters: MetadataFilters,
) -> bool:
    """Return whether a Qdrant collection has at least one matching point."""
    qdrant_filter = build_metadata_filter(filters)
    if qdrant_filter is None:
        return False

    try:
        points, _ = client.scroll(
            collection_name=collection_name,
            scroll_filter=qdrant_filter,
            limit=1,
            with_payload=False,
            with_vectors=False,
        )
        return bool(points)
    except Exception as exc:
        raise RuntimeError(
            f"Error checking for existing points in collection '{collection_name}'"
        ) from exc
