"""LangChain tool wrapper for deterministic EFTS retrieval hits."""

from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Any

from langchain_core.tools import StructuredTool

from sec_nlp.pipelines.presets.retrieve import RetrieveSettings
from sec_nlp.pipelines.presets.retrieve.steps import (
    rank_retrieval_hits,
    run_candidate_search,
)
from sec_nlp.pipelines.vector.config import VectorConfig

from .schemas import RetrieveHitsToolInput, RetrieveHitsToolOutput


def _check_timeout(
    *,
    started_at: float,
    timeout_seconds: float | None,
    stage: str,
) -> None:
    if timeout_seconds is None:
        return
    elapsed = monotonic() - started_at
    if elapsed > timeout_seconds:
        raise TimeoutError(
            f"retrieve_hits_tool timed out during {stage} after {elapsed:.2f}s"
        )


def _build_settings(
    *,
    symbols: list[str],
    queries: list[str],
    forms: list[str] | None,
    start_date,
    end_date,
    top_k: int,
    collection: str,
) -> RetrieveSettings:
    return RetrieveSettings(
        symbols=symbols,
        queries=queries,
        forms=forms,
        start_date=start_date,
        end_date=end_date,
        top_k=top_k,
        efts_candidates=max(200, top_k),
        dry_run=True,
        output_format="json",
        index_results=False,
        rerank_with_embeddings=False,
        dl_path=Path("./downloads"),
        out_path=Path("./outputs"),
        vdb=VectorConfig(collection_name=collection),
    )


def _run_retrieve_hits_tool(
    *,
    symbols: list[str],
    queries: list[str],
    forms: list[str] | None = None,
    start_date=None,
    end_date=None,
    top_k: int = 20,
    collection: str = "retrieve",
    timeout_seconds: float | None = 30.0,
) -> dict[str, Any]:
    started_at = monotonic()
    settings = _build_settings(
        symbols=symbols,
        queries=queries,
        forms=forms,
        start_date=start_date,
        end_date=end_date,
        top_k=top_k,
        collection=collection,
    )

    symbol_scope = settings.symbols if settings.symbols else [None]
    output_hits: list[dict[str, Any]] = []
    queries_processed = 0
    for symbol in symbol_scope:
        _check_timeout(
            started_at=started_at,
            timeout_seconds=timeout_seconds,
            stage=f"candidate search ({symbol or 'ALL'})",
        )
        candidates_by_query = run_candidate_search(
            symbol=symbol,
            queries=settings.queries,
            settings=settings,
        )
        ranked = rank_retrieval_hits(
            symbol=symbol or "ALL",
            candidates_by_query=candidates_by_query,
            top_k=settings.top_k,
        )
        output_hits.extend(
            hit.model_dump(mode="json", exclude_none=True) for hit in ranked
        )
        queries_processed += len(settings.queries)

    _check_timeout(
        started_at=started_at,
        timeout_seconds=timeout_seconds,
        stage="result aggregation",
    )
    output = RetrieveHitsToolOutput(
        collection=collection,
        run_metadata={
            "symbols_processed": len(symbol_scope),
            "queries_processed": queries_processed,
            "hits_returned": len(output_hits),
            "top_k": top_k,
            "forms": forms or [],
        },
        hits=output_hits,
    )
    return output.model_dump(mode="json", exclude_none=True)


retrieve_hits_tool = StructuredTool.from_function(
    name="retrieve_hits_tool",
    description=(
        "Return deterministic top-K EFTS retrieval hits for symbols and queries without LLM synthesis."
    ),
    func=_run_retrieve_hits_tool,
    args_schema=RetrieveHitsToolInput,
)
