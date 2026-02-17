"""Embedding rerank helpers for retrieve pipeline."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sec_nlp.core.infra.logger import logger

from ..config import RetrieveSettings
from ..models import RetrievalHit

_CACHE_SCHEMA_VERSION = 1


def _cache_key(
    *,
    model_name: str,
    text: str,
    prefix: str,
) -> str:
    payload = f"{model_name}|{prefix}|{text}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _normalize_vector(value: object) -> list[float] | None:
    if not isinstance(value, list):
        return None
    vector: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        vector.append(float(item))
    return vector


def _load_cache(path: Path) -> dict[str, list[float]]:
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug(
            "Failed to read retrieve embedding cache %s: %s", path, exc
        )
        return {}

    if not isinstance(payload, dict):
        return {}

    entries_raw = payload.get("entries")
    if not isinstance(entries_raw, dict):
        return {}

    entries: dict[str, list[float]] = {}
    for key, raw_vector in entries_raw.items():
        if not isinstance(key, str):
            continue
        vector = _normalize_vector(raw_vector)
        if vector is None:
            continue
        entries[key] = vector
    return entries


def _save_cache(
    *,
    path: Path,
    entries: dict[str, list[float]],
    max_entries: int,
) -> None:
    if max_entries > 0 and len(entries) > max_entries:
        overflow = len(entries) - max_entries
        for key in list(entries.keys())[:overflow]:
            entries.pop(key, None)

    payload = {
        "version": _CACHE_SCHEMA_VERSION,
        "entries": entries,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, separators=(",", ":"), sort_keys=False),
        encoding="utf-8",
    )


def _cached_text_embeddings(
    *,
    texts: Sequence[str],
    settings: RetrieveSettings,
    embedder: Any,
    cache_prefix: str,
) -> list[list[float]]:
    if not texts:
        return []

    if not settings.embedding_cache:
        return settings.vdb.batch_embed_documents(
            embedder,
            list(texts),
            show_progress=False,
        )

    cache_path = settings.embedding_cache_path()
    entries = _load_cache(cache_path)
    model_name = settings.vdb.embedding_model

    vectors: list[list[float]] = [[] for _ in texts]
    missing_indices: list[int] = []
    missing_texts: list[str] = []
    missing_keys: list[str] = []

    for idx, text in enumerate(texts):
        key = _cache_key(
            model_name=model_name,
            text=text,
            prefix=cache_prefix,
        )
        cached = entries.get(key)
        if cached is not None:
            # Touch key to retain most-recently used vectors when pruning.
            entries.pop(key, None)
            entries[key] = cached
            vectors[idx] = cached
            continue

        missing_indices.append(idx)
        missing_texts.append(text)
        missing_keys.append(key)

    if missing_texts:
        generated = settings.vdb.batch_embed_documents(
            embedder,
            missing_texts,
            show_progress=False,
        )
        for idx, key, raw_vector in zip(
            missing_indices, missing_keys, generated, strict=False
        ):
            vector = [float(x) for x in raw_vector] if raw_vector else []
            vectors[idx] = vector
            if vector:
                entries[key] = vector

        try:
            _save_cache(
                path=cache_path,
                entries=entries,
                max_entries=settings.embedding_cache_max_entries,
            )
        except Exception as exc:
            logger.debug(
                "Failed to write retrieve embedding cache %s: %s",
                cache_path,
                exc,
            )

    return vectors


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
        doc_vectors = _cached_text_embeddings(
            texts=texts,
            settings=settings,
            embedder=embedder,
            cache_prefix="snippet",
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


def embed_texts_with_cache(
    *,
    texts: Sequence[str],
    settings: RetrieveSettings,
    embedder: Any,
    cache_prefix: str = "snippet",
) -> list[list[float]]:
    """Embed text list with optional disk cache support."""

    return _cached_text_embeddings(
        texts=texts,
        settings=settings,
        embedder=embedder,
        cache_prefix=cache_prefix,
    )
