"""Download/chunk placeholder step for retrieve pipeline."""

from __future__ import annotations

from ..models import RetrievalHit


def passthrough_download_chunk(hits: list[RetrievalHit]) -> list[RetrievalHit]:
    """Placeholder until retrieve chunking/index stage is wired."""

    return hits
