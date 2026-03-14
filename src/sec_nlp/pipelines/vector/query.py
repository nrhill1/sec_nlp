# src/sec_nlp/pipelines/vector/query.py
"""Shared Qdrant query helpers for pipelines.

These helpers centralize small Qdrant access patterns used across pipeline
implementations so hot paths can batch existence checks and scans without
duplicating filter-building logic.
"""

from __future__ import annotations

from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.grpc.qdrant_common_pb2 import PointId
from qdrant_client.http.models import Record

from sec_nlp.pipelines.runtime import MetadataFilters, build_metadata_filter


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


def scroll_records(
    client: QdrantClient,
    collection_name: str,
    filters: MetadataFilters,
    *,
    limit: int = 100,
) -> list[Record]:
    """Return all matching Qdrant records for the provided metadata filter."""
    qdrant_filter = build_metadata_filter(filters)
    if qdrant_filter is None:
        return []

    records: list[Record] = []
    offset: int | str | UUID | PointId | None = None
    try:
        while True:
            points, next_offset = client.scroll(
                collection_name=collection_name,
                scroll_filter=qdrant_filter,
                limit=limit,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                break
            records.extend(points)
            if next_offset is None:
                break
            offset = next_offset
    except Exception as exc:
        raise RuntimeError(
            f"Error scrolling points from collection '{collection_name}'"
        ) from exc
    return records
