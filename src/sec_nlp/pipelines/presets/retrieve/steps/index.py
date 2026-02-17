"""Qdrant indexing helpers for retrieve pipeline."""

from __future__ import annotations

import hashlib
from uuid import NAMESPACE_URL, uuid5

from qdrant_client.models import Distance, PointStruct, VectorParams

from sec_nlp.core.infra.logger import logger
from sec_nlp.types import JsonValue

from ..config import RetrieveSettings
from ..models import RetrievalHit


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
    symbol: str, hit: RetrievalHit, settings: RetrieveSettings
) -> dict[str, JsonValue]:
    return {
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


def index_retrieval_hits(
    *,
    symbol: str,
    hits: list[RetrievalHit],
    settings: RetrieveSettings,
) -> list[RetrievalHit]:
    """Upsert retrieval hits into Qdrant when indexing is enabled."""

    if not hits or not settings.index_results:
        return hits
    if settings.dry_run:
        logger.info("Skipping retrieve indexing in dry_run mode")
        return hits

    try:
        embedder, embedding_dim = settings.vdb.setup_embedding_model()
        qdrant = settings.vdb.setup_qdrant_client()
        collection_name = _resolve_collection_name(settings)

        if not qdrant.collection_exists(collection_name):
            qdrant.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=embedding_dim,
                    distance=Distance.COSINE,
                ),
                replication_factor=settings.vdb.qdrant_replication_factor,
                write_consistency_factor=settings.vdb.qdrant_write_consistency_factor,
                on_disk_payload=settings.vdb.qdrant_on_disk_payload,
            )

        vectors = settings.vdb.batch_embed_documents(
            embedder,
            [hit.snippet or "" for hit in hits],
            show_progress=False,
        )

        points: list[PointStruct] = []
        for hit, vector in zip(hits, vectors, strict=False):
            if not vector:
                continue
            points.append(
                PointStruct(
                    id=_point_id(symbol, hit),
                    vector=list(vector),
                    payload=_payload(symbol, hit, settings),
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
