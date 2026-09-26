# src/sec_nlp/pipelines/presets/exb/steps/candidates.py
"""Candidate-first helpers for exhibit pipeline accession narrowing."""

from __future__ import annotations

from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines.common.ranking import (
    prune_hits_by_query_terms,
    rank_retrieval_hits,
)
from sec_nlp.pipelines.presets.retrieve.config import RetrieveSettings
from sec_nlp.pipelines.presets.retrieve.steps.candidate_search import (
    run_candidate_search,
)
from sec_nlp.pipelines.presets.retrieve.steps.tokenization import (
    DEFAULT_QUERY_STOPWORDS,
)

from ..config import ExhibitConfig


def _dedupe_queries(values: list[str]) -> list[str]:
    """Normalize and deduplicate candidate query strings."""
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in values:
        cleaned = raw.strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
    return deduped


def candidate_queries_for_exhibit(config: ExhibitConfig) -> list[str]:
    """Build EFTS candidate queries for exhibit accession narrowing."""
    if config.candidate_queries:
        return _dedupe_queries(list(config.candidate_queries))

    query_parts: list[str] = []
    query_parts.extend(config.search_terms)
    query_parts.extend(config.get_category_keywords())
    queries = _dedupe_queries(query_parts)
    if len(queries) > config.candidate_query_cap:
        return queries[: config.candidate_query_cap]
    return queries


def _candidate_settings(
    *,
    symbol: str,
    queries: list[str],
    config: ExhibitConfig,
) -> RetrieveSettings:
    """Build candidate-search settings from EXB config."""
    return RetrieveSettings(
        email=config.email,
        symbols=[symbol],
        forms=list(config.effective_forms),
        queries=list(queries),
        efts_candidates=config.efts_candidates,
        top_k=config.candidate_top_k,
        query_term_min_hits=config.candidate_query_term_min_hits,
        query_term_min_ratio=config.candidate_query_term_min_ratio,
        stopword_aware_lexical=config.candidate_stopword_aware_lexical,
        start_date=config.start_date,
        end_date=config.end_date,
        dl_path=config.dl_path,
        out_path=config.out_path,
        dry_run=True,
    )


def build_candidate_accessions(
    *,
    symbol: str,
    config: ExhibitConfig,
) -> set[str]:
    """Resolve ranked candidate accessions for a symbol using retrieve logic."""
    queries = candidate_queries_for_exhibit(config)
    if not queries:
        logger.warning(
            "EXB candidate-first enabled for %s but no candidate queries were provided",
            symbol,
        )
        return set()

    settings = _candidate_settings(
        symbol=symbol,
        queries=queries,
        config=config,
    )
    candidates_by_query = run_candidate_search(
        symbol=symbol,
        queries=queries,
        settings=settings,
    )
    if not candidates_by_query:
        return set()

    ranked_hits = rank_retrieval_hits(
        symbol=symbol,
        candidates_by_query=candidates_by_query,
        top_k=config.candidate_top_k,
    )
    if not ranked_hits:
        return set()

    stopwords = (
        DEFAULT_QUERY_STOPWORDS
        if config.candidate_stopword_aware_lexical
        else None
    )
    pruned_hits = prune_hits_by_query_terms(
        hits=ranked_hits,
        min_hits=config.candidate_query_term_min_hits,
        min_ratio=config.candidate_query_term_min_ratio,
        stopwords=stopwords,
    )
    selected = pruned_hits if pruned_hits else ranked_hits
    return {
        hit.accession_number for hit in selected if hit.accession_number.strip()
    }
