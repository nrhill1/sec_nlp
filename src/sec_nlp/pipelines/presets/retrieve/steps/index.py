"""Qdrant indexing helpers for retrieve pipeline."""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from sec_nlp.core.infra.logger import logger
from sec_nlp.types import JsonValue

from ..config import RetrieveSettings
from ..models import RetrievalHit
from .embed import embed_texts_with_cache


def _resolve_collection_name(settings: RetrieveSettings) -> str:
    configured = settings.vdb.collection_name
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    return "retrieve"


def _point_id(symbol: str, hit: RetrievalHit) -> str:
    raw = (
        f"{symbol}|{hit.query}|{hit.accession_number}|{hit.chunk_index}|"
        f"{hit.section_number}|{hit.filed_date}"
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return str(uuid5(NAMESPACE_URL, digest))


def _payload(
    symbol: str,
    hit: RetrievalHit,
    settings: RetrieveSettings,
    market_signals: dict[str, JsonValue] | None = None,
) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "symbol": symbol,
        "query": hit.query,
        "accession_number": hit.accession_number,
        "form_type": hit.form_type,
        "filed_date": hit.filed_date,
        "company_name": hit.company_name,
        "cik": hit.cik,
        "score": float(hit.score),
        "edgar_url": hit.edgar_url,
        "snippet": hit.snippet,
        "section_type": hit.section_type,
        "section_number": hit.section_number,
        "chunk_index": hit.chunk_index,
        "run_id": str(settings.run_id),
        "run_short_id": settings.short_id_display,
    }
    if settings.include_market_signals and market_signals:
        payload["market_signals"] = market_signals
    return payload


def _existing_point_ids(
    *,
    qdrant: QdrantClient,
    collection_name: str,
    point_ids: list[str],
    batch_size: int = 128,
) -> set[str]:
    existing: set[str] = set()
    for start in range(0, len(point_ids), batch_size):
        batch_ids = point_ids[start : start + batch_size]
        retrieved = qdrant.retrieve(
            collection_name=collection_name,
            ids=batch_ids,
            with_payload=False,
            with_vectors=False,
        )
        for point in retrieved:
            existing.add(str(point.id))
    return existing


def index_retrieval_hits(
    *,
    symbol: str,
    hits: list[RetrievalHit],
    settings: RetrieveSettings,
    qdrant_client: QdrantClient | None = None,
    embedder: Any | None = None,
    embedding_dim: int | None = None,
    market_signals: dict[str, JsonValue] | None = None,
) -> list[RetrievalHit]:
    """Upsert retrieval hits into Qdrant when indexing is enabled."""

    if not hits or not settings.index_results:
        return hits
    if settings.dry_run:
        logger.info("Skipping retrieve indexing in dry_run mode")
        return hits

    try:
        qdrant = qdrant_client or settings.vdb.setup_qdrant_client()
        collection_name = _resolve_collection_name(settings)
        has_collection = qdrant.collection_exists(collection_name)

        keyed_hits: list[tuple[RetrievalHit, str]] = [
            (hit, _point_id(symbol, hit)) for hit in hits
        ]
        if settings.incremental and has_collection:
            existing_ids = _existing_point_ids(
                qdrant=qdrant,
                collection_name=collection_name,
                point_ids=[point_id for _, point_id in keyed_hits],
            )
            if existing_ids:
                keyed_hits = [
                    (hit, point_id)
                    for hit, point_id in keyed_hits
                    if point_id not in existing_ids
                ]
                logger.info(
                    "Skipping %d already-indexed retrieve hits in '%s'",
                    len(existing_ids),
                    collection_name,
                )

        if not keyed_hits:
            logger.info(
                "All retrieve hits already indexed in '%s'; nothing to upsert",
                collection_name,
            )
            return hits

        active_embedder = embedder
        active_embedding_dim = embedding_dim
        if active_embedder is None or active_embedding_dim is None:
            active_embedder, active_embedding_dim = (
                settings.vdb.setup_embedding_model()
            )
        if not has_collection:
            qdrant.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=active_embedding_dim,
                    distance=Distance.COSINE,
                ),
                replication_factor=settings.vdb.qdrant_replication_factor,
                write_consistency_factor=settings.vdb.qdrant_write_consistency_factor,
                on_disk_payload=settings.vdb.qdrant_on_disk_payload,
            )

        vectors = embed_texts_with_cache(
            texts=[hit.snippet or "" for hit, _ in keyed_hits],
            settings=settings,
            embedder=active_embedder,
            cache_prefix="snippet",
        )

        points: list[PointStruct] = []
        for (hit, point_id), vector in zip(keyed_hits, vectors, strict=False):
            if not vector:
                continue
            points.append(
                PointStruct(
                    id=point_id,
                    vector=list(vector),
                    payload=_payload(
                        symbol,
                        hit,
                        settings,
                        market_signals=market_signals,
                    ),
                )
            )

        if not points:
            return hits

        qdrant.upsert(
            collection_name=collection_name,
            points=points,
            wait=True,
        )
        logger.info(
            "Indexed %d retrieve hits into '%s'",
            len(points),
            collection_name,
        )
        return hits
    except Exception as exc:
        logger.warning("Retrieve indexing skipped: %s", exc)
        return hits
