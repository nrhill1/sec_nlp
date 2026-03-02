# src/sec_nlp/pipelines/tools/vector.py
"""LangChain tool wrapper for direct Qdrant semantic search."""

from __future__ import annotations

from time import monotonic

from langchain_core.tools import StructuredTool
from qdrant_client.http.models import (
    Condition,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
)

from sec_nlp.core.types import as_json_dict
from sec_nlp.pipelines.vector.config import VectorConfig
from sec_nlp.types import JsonDict

from .schemas import QdrantSearchToolInput, QdrantSearchToolOutput


def _check_timeout(
    *,
    started_at: float,
    timeout_seconds: float | None,
    stage: str,
) -> None:
    """Raise timeout error when execution exceeds configured limit."""
    if timeout_seconds is None:
        return
    elapsed = monotonic() - started_at
    if elapsed > timeout_seconds:
        raise TimeoutError(
            f"qdrant_search_tool timed out during {stage} after {elapsed:.2f}s"
        )


def _build_filter(symbols: list[str], forms: list[str]) -> Filter | None:
    """Build Qdrant payload filter from tool input constraints."""
    must_conditions: list[Condition] = []
    if symbols:
        symbol_conditions: list[Condition] = []
        for symbol in symbols:
            symbol_conditions.extend(
                [
                    FieldCondition(
                        key="symbol", match=MatchValue(value=symbol)
                    ),
                    FieldCondition(
                        key="ticker", match=MatchValue(value=symbol)
                    ),
                    FieldCondition(
                        key="metadata.symbol",
                        match=MatchValue(value=symbol),
                    ),
                    FieldCondition(
                        key="metadata.ticker",
                        match=MatchValue(value=symbol),
                    ),
                ]
            )
        must_conditions.append(Filter(should=symbol_conditions))

    if forms:
        must_conditions.append(
            FieldCondition(key="form_type", match=MatchAny(any=forms))
        )
    if not must_conditions:
        return None
    return Filter(must=must_conditions)


def _run_qdrant_search_tool(
    *,
    collection: str,
    query: str,
    top_k: int = 20,
    symbols: list[str] | None = None,
    forms: list[str] | None = None,
    score_threshold: float | None = None,
    timeout_seconds: float | None = 30.0,
) -> JsonDict:
    """Execute qdrant search tool and return normalized hits."""
    started_at = monotonic()
    symbols = symbols or []
    forms = forms or []
    _check_timeout(
        started_at=started_at,
        timeout_seconds=timeout_seconds,
        stage="embedding setup",
    )

    vector_config = VectorConfig()
    embedder, _ = vector_config.setup_embedding_model()
    query_vector = embedder.embed_query(query)

    _check_timeout(
        started_at=started_at,
        timeout_seconds=timeout_seconds,
        stage="qdrant setup",
    )
    qdrant = vector_config.setup_qdrant_client()
    if not qdrant.collection_exists(collection):
        output = QdrantSearchToolOutput(
            collection=collection,
            query=query,
            hit_count=0,
            hits=[],
        )
        return output.model_dump(mode="json")

    query_filter = _build_filter(symbols, forms)
    response = qdrant.query_points(
        collection_name=collection,
        query=query_vector,
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
        with_vectors=False,
        score_threshold=score_threshold,
    )
    _check_timeout(
        started_at=started_at,
        timeout_seconds=timeout_seconds,
        stage="query_points",
    )

    hits: list[JsonDict] = []
    for point in getattr(response, "points", []):
        payload = getattr(point, "payload", {}) or {}
        if not isinstance(payload, dict):
            continue
        metadata = payload.get("metadata")
        metadata_dict = metadata if isinstance(metadata, dict) else {}
        snippet = (
            payload.get("snippet")
            or payload.get("content")
            or payload.get("text")
            or payload.get("page_content")
        )
        hits.append(
            {
                "score": float(getattr(point, "score", 0.0) or 0.0),
                "symbol": payload.get("symbol")
                or payload.get("ticker")
                or metadata_dict.get("symbol"),
                "accession_number": payload.get("accession_number")
                or metadata_dict.get("accession_number"),
                "form_type": payload.get("form_type")
                or metadata_dict.get("form_type"),
                "filed_date": payload.get("filed_date")
                or metadata_dict.get("filed_date"),
                "source": payload.get("source")
                or payload.get("edgar_url")
                or metadata_dict.get("source"),
                "snippet": snippet,
            }
        )

    output = QdrantSearchToolOutput(
        collection=collection,
        query=query,
        hit_count=len(hits),
        hits=hits,
    )
    payload = as_json_dict(output.model_dump(mode="json", exclude_none=True))
    if payload is None:
        raise ValueError("qdrant_search_tool produced a non-JSON payload")
    return payload


qdrant_search_tool = StructuredTool.from_function(
    name="qdrant_search_tool",
    description=(
        "Run direct semantic search against a Qdrant collection with optional symbol/form filters."
    ),
    func=_run_qdrant_search_tool,
    args_schema=QdrantSearchToolInput,
)
