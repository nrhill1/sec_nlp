"""Embedding placeholder step for retrieve pipeline."""

from __future__ import annotations

from ..models import RetrievalHit


def passthrough_embed(hits: list[RetrievalHit]) -> list[RetrievalHit]:
    """Placeholder until crates/embed integration is available."""

    return hits
