"""Embedding rerank helpers for retrieve pipeline."""

from __future__ import annotations

import math
from collections.abc import Sequence

from sec_nlp.core.infra.logger import logger

from ..config import RetrieveSettings
from ..models import RetrievalHit


def _cosine_similarity(
    left: Sequence[float],
    right: Sequence[float],
) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    denom = left_norm * right_norm
    if denom == 0:
        return 0.0
    return dot / denom


def rerank_with_embeddings(
    *,
    hits: list[RetrievalHit],
    settings: RetrieveSettings,
) -> list[RetrievalHit]:
    """Rerank hits using query/snippet embedding similarity when enabled."""

    if not hits or not settings.rerank_with_embeddings:
        return hits

    try:
        embedder, _ = settings.vdb.setup_embedding_model()
        texts = [hit.snippet or "" for hit in hits]
        doc_vectors = settings.vdb.batch_embed_documents(
            embedder,
            texts,
            show_progress=False,
        )
        query_vectors: dict[str, list[float]] = {}
        reranked: list[RetrievalHit] = []
        weight = settings.embedding_weight

        for hit, doc_vector in zip(hits, doc_vectors, strict=False):
            query_key = hit.query
            if query_key not in query_vectors:
                query_vectors[query_key] = list(embedder.embed_query(query_key))
            similarity = _cosine_similarity(
                query_vectors[query_key], doc_vector
            )
            blended = ((1.0 - weight) * float(hit.score)) + (
                weight * similarity
            )
            reranked.append(
                hit.model_copy(
                    update={
                        "score": float(blended),
                    }
                )
            )

        reranked.sort(
            key=lambda hit: (
                hit.score,
                hit.filed_date,
                hit.query.casefold(),
                hit.accession_number,
            ),
            reverse=True,
        )
        return reranked
    except Exception as exc:
        logger.warning(
            "Embedding rerank unavailable; using lexical ranking only: %s",
            exc,
        )
        return hits
