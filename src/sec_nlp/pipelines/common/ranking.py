# src/sec_nlp/pipelines/common/ranking.py
"""Shared ranking and lexical pruning helpers for retrieval-style hits."""

from __future__ import annotations

import heapq
from collections.abc import Collection
from datetime import date

from sec_nlp.core.edgar.efts_models import EFTSHit
from sec_nlp.pipelines.presets.retrieve.models import RetrievalHit
from sec_nlp.pipelines.presets.retrieve.steps.tokenization import (
    extract_query_terms,
)


def _rank_key(
    *,
    score: float,
    filed_date: date,
    query: str,
    accession: str,
) -> tuple[float, date, str, str]:
    """Build deterministic sort key for ranking tuples."""
    return (score, filed_date, query.casefold(), accession)


def rank_retrieval_hits(
    *,
    symbol: str,
    candidates_by_query: dict[str, list[EFTSHit]],
    top_k: int,
) -> list[RetrievalHit]:
    """Rank flattened EFTS candidates and return top K rows."""

    if top_k <= 0:
        return []

    ranked_heap: list[tuple[tuple[float, date, str, str], RetrievalHit]] = []
    seen: set[tuple[str, str]] = set()

    for query, hits in candidates_by_query.items():
        for hit in hits:
            key = (query.casefold(), hit.accession_number)
            if key in seen:
                continue
            seen.add(key)
            retrieval_hit = RetrievalHit(
                symbol=symbol,
                query=query,
                accession_number=hit.accession_number,
                form_type=hit.form_type,
                filed_date=hit.filed_date.isoformat(),
                company_name=hit.company_name,
                cik=hit.cik,
                score=float(hit.score),
                edgar_url=hit.edgar_url,
                snippet=hit.snippet or None,
            )
            rank_key = _rank_key(
                score=float(hit.score),
                filed_date=hit.filed_date,
                query=query,
                accession=hit.accession_number,
            )

            if len(ranked_heap) < top_k:
                heapq.heappush(ranked_heap, (rank_key, retrieval_hit))
                continue

            if rank_key > ranked_heap[0][0]:
                heapq.heapreplace(ranked_heap, (rank_key, retrieval_hit))

    ranked_heap.sort(key=lambda item: item[0], reverse=True)
    return [hit for _, hit in ranked_heap]


def _query_terms(
    query: str,
    *,
    min_len: int = 3,
    stopwords: Collection[str] | None = None,
) -> set[str]:
    """Extract normalized query terms from hit metadata."""
    return extract_query_terms(
        query,
        min_len=min_len,
        stopwords=stopwords,
    )


def prune_hits_by_query_terms(
    *,
    hits: list[RetrievalHit],
    min_hits: int,
    min_ratio: float,
    min_term_len: int = 3,
    stopwords: Collection[str] | None = None,
) -> list[RetrievalHit]:
    """Prune retrieval hits by lexical query-term overlap.

    Args:
        hits: Ranked retrieval hits.
        min_hits: Minimum matched query terms required. Set to 0 to disable.
        min_ratio: Minimum matched/query-term ratio required. Set to 0 to disable.
        min_term_len: Minimum length of query terms used for matching.
    """
    if not hits:
        return []
    if min_hits <= 0 and min_ratio <= 0:
        return list(hits)

    kept: list[RetrievalHit] = []
    for hit in hits:
        terms = _query_terms(
            hit.query,
            min_len=min_term_len,
            stopwords=stopwords,
        )
        if not terms:
            kept.append(hit)
            continue

        snippet_terms_all = _query_terms(
            hit.snippet or "",
            min_len=min_term_len,
        )
        # EFTS snippets can be very short or sparse; skip lexical gating when
        # snippet evidence is too limited to evaluate overlap reliably.
        if len(snippet_terms_all) < max(3, min_hits * 3):
            kept.append(hit)
            continue
        snippet_terms = _query_terms(
            hit.snippet or "",
            min_len=min_term_len,
            stopwords=stopwords,
        )
        if not snippet_terms:
            kept.append(hit)
            continue

        matched = len(terms.intersection(snippet_terms))

        if min_hits > 0 and matched < min_hits:
            continue
        ratio = matched / len(terms)
        if min_ratio > 0 and ratio < min_ratio:
            continue
        kept.append(hit)
    return kept
