"""Embedding rerank helpers for retrieve pipeline."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from sec_nlp.core.infra.logger import logger

from ..config import RetrieveSettings
from ..models import RetrievalHit

_CACHE_BATCH_SIZE = 400


def _cache_key(
    *,
    model_name: str,
    text: str,
    prefix: str,
) -> str:
    payload = f"{model_name}|{prefix}|{text}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _coerce_vector(value) -> list[float] | None:
    if value is None or isinstance(value, (str, bytes, bytearray)):
        return None
    if not isinstance(value, Iterable):
        return None

    iterator = iter(value)
    vector: list[float] = []
    for item in iterator:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        vector.append(float(item))
    return vector


def _embed_documents(
    *,
    texts: Sequence[str],
    settings: RetrieveSettings,
    embedder,
) -> list[list[float]]:
    raw_vectors = settings.vdb.batch_embed_documents(
        embedder,
        list(texts),
        show_progress=False,
    )
    vectors: list[list[float]] = []
    for raw_vector in raw_vectors:
        vector = _coerce_vector(raw_vector)
        vectors.append(vector or [])
    if len(vectors) < len(texts):
        vectors.extend([[] for _ in range(len(texts) - len(vectors))])
    return vectors[: len(texts)]


def _cache_db_path(path: Path) -> Path:
    if path.suffix.casefold() == ".json":
        return path.with_suffix(".sqlite3")
    return path


def _open_cache_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            cache_key TEXT PRIMARY KEY,
            vector_json TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_embeddings_updated_at
        ON embeddings(updated_at)
        """
    )
    return conn


def _chunked_keys(keys: Sequence[str]) -> Iterator[Sequence[str]]:
    for idx in range(0, len(keys), _CACHE_BATCH_SIZE):
        yield keys[idx : idx + _CACHE_BATCH_SIZE]


def _legacy_json_entries(path: Path) -> dict[str, list[float]]:
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug(
            "Failed to read legacy retrieve embedding cache %s: %s",
            path,
            exc,
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
        vector = _coerce_vector(raw_vector)
        if vector is not None:
            entries[key] = vector
    return entries


def _cache_read(
    *,
    conn: sqlite3.Connection,
    keys: Sequence[str],
) -> dict[str, list[float]]:
    if not keys:
        return {}

    found: dict[str, list[float]] = {}
    for batch in _chunked_keys(keys):
        placeholders = ",".join("?" for _ in batch)
        query = f"SELECT cache_key, vector_json FROM embeddings WHERE cache_key IN ({placeholders})"
        for key, vector_json in conn.execute(query, tuple(batch)).fetchall():
            try:
                parsed = json.loads(vector_json)
            except Exception:
                continue
            vector = _coerce_vector(parsed)
            if vector is not None:
                found[key] = vector
    return found


def _cache_touch(
    *,
    conn: sqlite3.Connection,
    keys: Sequence[str],
    updated_at: int,
) -> None:
    if not keys:
        return
    conn.executemany(
        "UPDATE embeddings SET updated_at = ? WHERE cache_key = ?",
        [(updated_at, key) for key in keys],
    )


def _cache_upsert(
    *,
    conn: sqlite3.Connection,
    entries: dict[str, list[float]],
    updated_at: int,
) -> None:
    if not entries:
        return
    conn.executemany(
        """
        INSERT INTO embeddings (cache_key, vector_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(cache_key)
        DO UPDATE SET
            vector_json = excluded.vector_json,
            updated_at = excluded.updated_at
        """,
        [
            (
                key,
                json.dumps(vector, separators=(",", ":"), sort_keys=False),
                updated_at,
            )
            for key, vector in entries.items()
        ],
    )


def _cache_prune(
    *,
    conn: sqlite3.Connection,
    max_entries: int,
) -> None:
    if max_entries <= 0:
        return
    row = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()
    count = int(row[0]) if row else 0
    overflow = count - max_entries
    if overflow <= 0:
        return
    conn.execute(
        """
        DELETE FROM embeddings
        WHERE cache_key IN (
            SELECT cache_key
            FROM embeddings
            ORDER BY updated_at ASC, cache_key ASC
            LIMIT ?
        )
        """,
        (overflow,),
    )


def _migrate_legacy_json_cache(
    *,
    conn: sqlite3.Connection,
    legacy_path: Path,
) -> None:
    if not legacy_path.exists():
        return
    row = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()
    count = int(row[0]) if row else 0
    if count > 0:
        return

    entries = _legacy_json_entries(legacy_path)
    if not entries:
        return

    updated_at = int(time.time())
    _cache_upsert(conn=conn, entries=entries, updated_at=updated_at)
    logger.info(
        "Migrated %s retrieve embedding cache entries from %s",
        len(entries),
        legacy_path,
    )


def _cached_text_embeddings(
    *,
    texts: Sequence[str],
    settings: RetrieveSettings,
    embedder,
    cache_prefix: str,
) -> list[list[float]]:
    if not texts:
        return []

    if not settings.embedding_cache:
        return _embed_documents(
            texts=texts,
            settings=settings,
            embedder=embedder,
        )

    cache_file = settings.embedding_cache_path()
    cache_db = _cache_db_path(cache_file)
    model_name = settings.vdb.embedding_model

    try:
        conn = _open_cache_db(cache_db)
    except Exception as exc:
        logger.debug(
            "Failed to open retrieve embedding cache DB %s: %s",
            cache_db,
            exc,
        )
        return _embed_documents(
            texts=texts,
            settings=settings,
            embedder=embedder,
        )

    text_keys = [
        _cache_key(
            model_name=model_name,
            text=text,
            prefix=cache_prefix,
        )
        for text in texts
    ]

    try:
        with conn:
            if cache_file != cache_db:
                _migrate_legacy_json_cache(conn=conn, legacy_path=cache_file)

            cached_vectors = _cache_read(conn=conn, keys=text_keys)
            touched: set[str] = set()
            missing_positions: dict[str, list[int]] = {}
            missing_text_by_key: dict[str, str] = {}
            vectors: list[list[float]] = [[] for _ in texts]

            for idx, key in enumerate(text_keys):
                cached = cached_vectors.get(key)
                if cached is not None:
                    vectors[idx] = cached
                    touched.add(key)
                    continue
                positions = missing_positions.setdefault(key, [])
                positions.append(idx)
                missing_text_by_key.setdefault(key, texts[idx])

            now = int(time.time())
            _cache_touch(conn=conn, keys=list(touched), updated_at=now)

            if missing_text_by_key:
                missing_items = list(missing_text_by_key.items())
                missing_keys = [key for key, _ in missing_items]
                missing_texts = [text for _, text in missing_items]
                generated = _embed_documents(
                    texts=missing_texts,
                    settings=settings,
                    embedder=embedder,
                )
                fresh_entries: dict[str, list[float]] = {}
                for key, vector in zip(
                    missing_keys,
                    generated,
                    strict=False,
                ):
                    for idx in missing_positions.get(key, []):
                        vectors[idx] = vector
                    if vector:
                        fresh_entries[key] = vector

                _cache_upsert(
                    conn=conn,
                    entries=fresh_entries,
                    updated_at=now,
                )

            _cache_prune(
                conn=conn,
                max_entries=settings.embedding_cache_max_entries,
            )
            return vectors
    except Exception as exc:
        logger.debug(
            "Failed to use retrieve embedding cache DB %s: %s",
            cache_db,
            exc,
        )
        return _embed_documents(
            texts=texts,
            settings=settings,
            embedder=embedder,
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


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
    embedder=None,
    allow_setup_fallback: bool = True,
) -> list[RetrievalHit]:
    """Rerank hits using query/snippet embedding similarity when enabled."""

    if not hits or not settings.rerank_with_embeddings:
        return hits

    try:
        active_embedder = embedder
        if active_embedder is None:
            if not allow_setup_fallback:
                return hits
            active_embedder, _ = settings.vdb.setup_embedding_model()
        texts = [hit.snippet or "" for hit in hits]
        doc_vectors = _cached_text_embeddings(
            texts=texts,
            settings=settings,
            embedder=active_embedder,
            cache_prefix="snippet",
        )
        query_vectors: dict[str, list[float]] = {}
        reranked: list[RetrievalHit] = []
        weight = settings.embedding_weight

        for hit, doc_vector in zip(hits, doc_vectors, strict=False):
            query_key = hit.query
            if query_key not in query_vectors:
                query_vectors[query_key] = list(
                    active_embedder.embed_query(query_key)
                )
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
    embedder,
    cache_prefix: str = "snippet",
) -> list[list[float]]:
    """Embed text list with optional disk cache support."""

    return _cached_text_embeddings(
        texts=texts,
        settings=settings,
        embedder=embedder,
        cache_prefix=cache_prefix,
    )
