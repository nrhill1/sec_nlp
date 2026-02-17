"""Index placeholder step for retrieve pipeline."""

from __future__ import annotations

from ..models import RetrievalHit


def passthrough_index(hits: list[RetrievalHit]) -> list[RetrievalHit]:
    """Placeholder until Qdrant upsert flow is wired for retrieve."""

    return hits
