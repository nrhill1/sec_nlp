# src/sec_nlp/pipelines/presets/analyze/runnables/search.py
"""Vector search utilities for the analyze pipeline."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from langchain_core.documents import Document
from langchain_core.runnables import RunnableConfig, RunnableSerializable
from langchain_qdrant import QdrantVectorStore
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.infra.logger import log_divider, logger
from sec_nlp.core.types import coerce_bool, coerce_float
from sec_nlp.pipelines.metadata.filters import (
    MetadataFilters,
    build_metadata_filter,
)
from sec_nlp.pipelines.metadata.normalize import normalize_metadata_for_output
from sec_nlp.pipelines.output_io import write_yaml
from sec_nlp.pipelines.serialization import round_score
from sec_nlp.types import JsonDict, JsonValue

from ..steps.search.payloads import (
    SearchHighlightsPayload,
    SearchMatchPayload,
    SearchQuerySectionPayload,
    SearchResultPayload,
    SearchStatsPayload,
    SearchSummaryPayload,
    SearchUniqueResultPayload,
)
from ..utils import query_term_overlap, resolve_symbol_for_output
from .analysis import AnalysisBatchInput


@dataclass(frozen=True)
class SearchQueryResults:
    filtered: list[tuple[Document, float]]
    total: int


type SearchResultsByQuery = dict[str, SearchQueryResults]


@dataclass
class _UniqueHit:
    doc: Document
    matches: dict[str, float]


class SearchRetrieveInput(BaseModel):
    """Runnable input for retrieving search hits."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    symbol: str | None = None
    queries: list[str] | None = None


class SearchRunnable(
    RunnableSerializable[SearchRetrieveInput, AnalysisBatchInput]
):
    """Run semantic search for queries."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    symbols: list[str] = Field(default_factory=list)
    vector_mode: Literal["off", "read", "write"] = Field(default="write")
    search_limit: int = Field(default=10, ge=1)
    score_threshold: float = Field(default=0.4, ge=0.0)
    metadata_filters: MetadataFilters = Field(default_factory=dict)
    query_term_min_hits: int = Field(default=1, ge=0)
    query_term_min_ratio: float = Field(default=0.3, ge=0.0)
    query_term_min_len: int = Field(default=3, ge=1)
    search_analyze: bool = Field(default=True)
    export_results_enabled: bool = Field(default=True)
    distance_metric: str = Field(default="Cosine")
    search_type: str = Field(
        default="similarity",
        description="Search type: 'similarity' or 'mmr' (maximal marginal relevance)",
    )
    output_root: Path = Field(default=Path("./outputs"))
    pipeline_type: str = Field(default="analyze")
    run_dir: str = Field(default="")
    vector_store: QdrantVectorStore | None = Field(
        default=None, description="Vector store backend"
    )

    def invoke(
        self,
        input: SearchRetrieveInput,
        config: RunnableConfig | None = None,
        **kwargs: JsonValue,
    ) -> AnalysisBatchInput:
        """Invoke the runnable for chaining in a sequence."""
        _ = config
        _ = kwargs
        queries = input.queries
        docs = self.retrieve_hits(queries)
        fallback_symbol = input.symbol or (
            self.symbols[0] if self.symbols else "<unknown>"
        )
        return AnalysisBatchInput(symbol=fallback_symbol, docs=docs)

    def search_queries(
        self, queries: list[str] | None = None
    ) -> SearchResultsByQuery:
        """Run similarity search per query and return filtered hits."""
        query_list = queries or []
        query_list = self._clean_queries(query_list)
        if not self.vector_store or not query_list or self.vector_mode == "off":
            return {}

        distance_metric = self.distance_metric
        distance_prefers_lower = distance_metric in ("Cosine", "Euclid")
        threshold = self.score_threshold
        metadata_filter = build_metadata_filter(self.metadata_filters)
        try:
            collection = self.vector_store.collection_name
            client = self.vector_store.client
            if collection and client:
                count = client.count(collection, exact=True).count
                logger.info(
                    "Vector search using collection=%s (points=%d)",
                    collection,
                    count,
                )
        except Exception:
            logger.debug("Could not fetch Qdrant count before search")

        results_by_query: SearchResultsByQuery = {}

        for query in query_list:
            if self.search_type == "mmr":
                # MMR search for diversity
                docs = self.vector_store.max_marginal_relevance_search(
                    query=query,
                    k=self.search_limit,
                    fetch_k=self.search_limit * 2,
                    lambda_mult=0.5,  # Balance diversity vs relevance
                    filter=metadata_filter,
                )
                # MMR doesn't return scores, assign rank-based scores
                results = [
                    (doc, 1.0 - (i / max(len(docs), 1)))
                    for i, doc in enumerate(docs)
                ]
            else:
                # Standard similarity search
                results = self.vector_store.similarity_search_with_score(
                    query,
                    k=self.search_limit,
                    filter=metadata_filter,
                )

            # For MMR, scores are rank-based (1.0 for best, decreasing), not distances
            # So we skip distance threshold filtering for MMR
            if self.search_type == "mmr":
                filtered = [
                    (doc, score)
                    for doc, score in results
                    if self._passes_query_term_gate(query, doc.page_content)
                ]
            else:
                filtered = [
                    (doc, score)
                    for doc, score in results
                    if (
                        score <= threshold
                        if distance_prefers_lower
                        else score >= threshold
                    )
                    and self._passes_query_term_gate(query, doc.page_content)
                ]
            results_by_query[query] = SearchQueryResults(
                filtered=filtered,
                total=len(results),
            )

        return results_by_query

    def retrieve_hits(self, queries: list[str] | None = None) -> list[Document]:
        """Retrieve candidate chunks from the vector store."""
        docs, _ = self.retrieve_hits_with_results(queries)
        return docs

    def retrieve_hits_with_results(
        self, queries: list[str] | None = None
    ) -> tuple[list[Document], SearchResultsByQuery]:
        """Retrieve deduplicated hits plus per-query results for export."""
        results_by_query = self.search_queries(queries)
        if not results_by_query:
            return [], results_by_query

        distance_metric = self.distance_metric
        distance_prefers_lower = distance_metric in ("Cosine", "Euclid")

        unique_hits: dict[tuple[str | None, str | None, str], _UniqueHit] = {}

        for query, query_results in results_by_query.items():
            for doc, score in query_results.filtered:
                key = self._build_unique_hit_key(doc)
                hit = unique_hits.get(key)
                score_value = float(score)
                if hit is None:
                    unique_hits[key] = _UniqueHit(
                        doc=doc,
                        matches={query: score_value},
                    )
                else:
                    self._update_match(
                        hit.matches,
                        query,
                        score_value,
                        distance_prefers_lower,
                    )

        retrieved: list[Document] = []
        for hit in unique_hits.values():
            matched_queries = self._sort_matches(
                hit.matches, distance_prefers_lower
            )
            metadata = {**(hit.doc.metadata or {})}
            metadata["matched_queries"] = [
                {"query": query, "score": score}
                for query, score in matched_queries
            ]
            retrieved.append(
                Document(
                    page_content=hit.doc.page_content,
                    metadata=metadata,
                )
            )

        return retrieved, results_by_query

    def _passes_query_term_gate(
        self, query: str | None, content: str | None
    ) -> bool:
        min_hits = self.query_term_min_hits
        min_ratio = self.query_term_min_ratio
        min_len = self.query_term_min_len
        if min_hits <= 0 and min_ratio <= 0:
            return True
        matched_terms, _, ratio = query_term_overlap(
            query,
            content,
            min_len=min_len,
        )
        hits = len(matched_terms)
        if min_hits > 0 and hits < min_hits:
            return False
        if min_ratio > 0 and ratio < min_ratio:
            return False
        return True

    @staticmethod
    def _build_unique_hit_key(
        doc: Document,
        *,
        fallback_symbol: str | None = None,
    ) -> tuple[str | None, str | None, str]:
        meta = doc.metadata or {}
        symbol_value = meta.get("symbol") or meta.get("ticker")
        symbol = (
            str(symbol_value).strip().upper()
            if isinstance(symbol_value, str) and symbol_value.strip()
            else None
        )
        if symbol is None and isinstance(fallback_symbol, str):
            fallback = fallback_symbol.strip().upper()
            symbol = fallback if fallback else None
        accession_value = meta.get("accession_number") or meta.get("accession")
        accession = (
            str(accession_value).strip()
            if isinstance(accession_value, str) and accession_value.strip()
            else None
        )
        section_value = meta.get("section_number")
        section = (
            str(section_value).strip() if section_value is not None else ""
        )
        simhash_value = meta.get("simhash")
        if isinstance(simhash_value, (int, float)):
            content_key = f"simhash:{int(simhash_value)}"
        elif isinstance(simhash_value, str) and simhash_value.strip():
            content_key = f"simhash:{simhash_value.strip()}"
        else:
            chunk_index = meta.get("chunk_index")
            if isinstance(chunk_index, (int, float, str)):
                content_key = f"chunk:{chunk_index}"
            else:
                content_key = f"len:{len(doc.page_content or '')}"
        return (symbol, accession, f"{section}|{content_key}")

    def run(self, queries: list[str] | None = None) -> list[Path]:
        """Run semantic search queries if configured."""
        query_list = queries or []
        query_list = self._clean_queries(query_list)
        if not query_list:
            logger.warning(
                "Search not configured: no queries or topics provided"
            )
            return []

        if not self.vector_store:
            logger.warning(
                "Search queries configured but vector store not initialized "
                "(vector_mode may be 'off'?)"
            )
            return []
        if self.search_analyze:
            logger.info(
                "Search export analysis disabled; run the analyze chain instead"
            )

        results_by_query = self.search_queries(query_list)
        return self.export_results(results_by_query, queries=query_list)

    def export_results(
        self,
        results_by_query: SearchResultsByQuery,
        *,
        cached: bool = False,
        queries: list[str] | None = None,
    ) -> list[Path]:
        """Export search results from precomputed hits."""
        query_list = queries or []
        query_list = self._clean_queries(query_list)
        if not query_list:
            logger.warning(
                "Search not configured: no queries or topics provided"
            )
            return []
        if not self.export_results_enabled:
            logger.info("Search export disabled; skipping results export")
            return []

        if cached:
            logger.info("Reusing cached search results for export")

        log_divider(logger, color="yellow")
        logger.info(
            "Exporting results for %d semantic search queries",
            len(query_list),
        )

        distance_metric = self.distance_metric
        distance_prefers_lower = distance_metric in ("Cosine", "Euclid")
        threshold = self.score_threshold
        metadata_filters_payload = self._build_metadata_filters_payload(
            self.metadata_filters
        )

        per_symbol_query_results: dict[
            str, dict[str, list[tuple[Document, float]]]
        ] = defaultdict(lambda: defaultdict(list))
        unique_hits: dict[
            str, dict[tuple[str | None, str | None, str], _UniqueHit]
        ] = defaultdict(dict)

        for i, query in enumerate(query_list, 1):
            try:
                logger.info(
                    "[%d/%d] Query: %s",
                    i,
                    len(query_list),
                    query,
                )

                query_results = results_by_query.get(query)
                if query_results is None:
                    filtered_results: list[tuple[Document, float]] = []
                    total_results = 0
                else:
                    filtered_results = query_results.filtered
                    total_results = query_results.total

                logger.info(
                    "Search '%s': kept %d/%d (%s %.2f)",
                    query,
                    len(filtered_results),
                    total_results,
                    "<=" if distance_prefers_lower else ">=",
                    threshold,
                )

                for doc, score in filtered_results:
                    meta = doc.metadata or {}
                    symbol_for_output = resolve_symbol_for_output(
                        self.symbols[0] if self.symbols else "<unknown>",
                        meta,
                    )
                    per_symbol_query_results[symbol_for_output][query].append(
                        (doc, score)
                    )

                    key = self._build_unique_hit_key(
                        doc, fallback_symbol=symbol_for_output
                    )
                    hit = unique_hits[symbol_for_output].get(key)
                    score_value = float(score)
                    if hit is None:
                        unique_hits[symbol_for_output][key] = _UniqueHit(
                            doc=doc,
                            matches={query: score_value},
                        )
                    else:
                        self._update_match(
                            hit.matches,
                            query,
                            score_value,
                            distance_prefers_lower,
                        )

                logger.info("  -> Found %d results", len(filtered_results))

            except Exception as e:
                logger.error("Search failed for query '%s': %s", query, e)
                continue

        if not per_symbol_query_results:
            logger.info("No search results to export")
            return []

        search_outputs: list[Path] = []

        for symbol_key, query_results_map in per_symbol_query_results.items():
            output_dir = self._get_symbol_output_dir(symbol_key) / "search"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / "summary.yaml"

            query_sections: list[SearchQuerySectionPayload] = []
            for query in query_list:
                symbol_results = query_results_map.get(query, [])

                section_counts: dict[str, int] = defaultdict(int)
                tag_counts: dict[str, int] = defaultdict(int)
                sentiment_counts: dict[str, int] = defaultdict(int)

                scores = [float(score) for _, score in symbol_results]
                avg_score = sum(scores) / len(scores) if scores else None
                best_score = self._best_score(scores, distance_prefers_lower)

                top_summaries: list[str] = []

                for doc, _ in symbol_results:
                    meta = doc.metadata or {}

                    section = meta.get("section_number")
                    if section:
                        section_counts[str(section)] += 1

                    for tag in meta.get("tags") or []:
                        tag_counts[str(tag)] += 1

                    sentiment = meta.get("sentiment")
                    if sentiment:
                        sentiment_counts[str(sentiment)] += 1

                    summary = meta.get("summary")
                    if (
                        isinstance(summary, str)
                        and summary
                        and summary not in top_summaries
                    ):
                        top_summaries.append(summary)

                results_payload = [
                    SearchResultPayload(
                        score=self._round_score(float(score)) or 0.0,
                        content=(doc.page_content or "")[:500],
                        metadata=(
                            metadata_payload := normalize_metadata_for_output(
                                doc.metadata
                            )
                        ),
                        summary=metadata_payload.get("summary"),
                        tags=metadata_payload.get("tags"),
                        sentiment=metadata_payload.get("sentiment"),
                        forward_looking=coerce_bool(
                            metadata_payload.get("forward_looking")
                        ),
                        confidence_score=self._round_score(
                            coerce_float(
                                metadata_payload.get("confidence_score")
                            )
                        ),
                    )
                    for doc, score in symbol_results
                ]

                stats_payload = SearchStatsPayload(
                    average_score=self._round_score(avg_score),
                    best_score=self._round_score(best_score),
                    symbols=(
                        {symbol_key: len(symbol_results)}
                        if symbol_results
                        else {}
                    ),
                    sections=dict(section_counts),
                    tag_frequency=dict(
                        sorted(
                            tag_counts.items(),
                            key=lambda t: t[1],
                            reverse=True,
                        )
                    ),
                    sentiment_breakdown=dict(sentiment_counts),
                )

                highlights_payload = SearchHighlightsPayload(
                    top_summaries=top_summaries[:10]
                )

                query_sections.append(
                    SearchQuerySectionPayload(
                        query=query,
                        results_count=len(symbol_results),
                        stats=stats_payload,
                        highlights=highlights_payload,
                        results=results_payload,
                    )
                )

            unique_payloads = self._build_unique_results(
                unique_hits.get(symbol_key, {}),
                distance_prefers_lower,
            )

            summary_payload = SearchSummaryPayload(
                symbol=symbol_key,
                score_threshold=threshold,
                metadata_filters=metadata_filters_payload,
                total_queries=len(query_list),
                total_unique_results=len(unique_payloads),
                queries=query_sections,
                unique_results=unique_payloads,
            )

            write_yaml(
                output_file,
                summary_payload,
                exclude_none=True,
                sort_keys=False,
                allow_unicode=True,
            )

            search_outputs.append(output_file)
            logger.info(
                "Exported consolidated search results to %s",
                output_file,
            )

        return search_outputs

    def _get_symbol_output_dir(self, symbol: str) -> Path:
        normalized_symbol = symbol.strip().upper()
        run_component = self.run_dir or "run"
        symbol_out_path = (
            self.output_root
            / run_component
            / self.pipeline_type
            / normalized_symbol
        )
        symbol_out_path.mkdir(parents=True, exist_ok=True)
        return symbol_out_path

    @staticmethod
    def _clean_queries(queries: list[str] | None) -> list[str]:
        if not queries:
            return []
        return [
            query.strip()
            for query in queries
            if isinstance(query, str) and query.strip()
        ]

    @staticmethod
    def _round_score(value: float | None) -> float | None:
        return round_score(value)

    @staticmethod
    def _score_is_better(
        candidate: float, current: float, prefers_lower: bool
    ) -> bool:
        return candidate < current if prefers_lower else candidate > current

    @classmethod
    def _update_match(
        cls,
        matches: dict[str, float],
        query: str,
        score: float,
        prefers_lower: bool,
    ) -> None:
        existing = matches.get(query)
        if existing is None or cls._score_is_better(
            score, existing, prefers_lower
        ):
            matches[query] = score

    @staticmethod
    def _sort_matches(
        matches: dict[str, float], prefers_lower: bool
    ) -> list[tuple[str, float]]:
        if prefers_lower:
            return sorted(matches.items(), key=lambda item: (item[1], item[0]))
        return sorted(matches.items(), key=lambda item: (-item[1], item[0]))

    @staticmethod
    def _best_score(scores: list[float], prefers_lower: bool) -> float | None:
        if not scores:
            return None
        return min(scores) if prefers_lower else max(scores)

    @staticmethod
    def _unique_sort_key(
        payload: SearchUniqueResultPayload, prefers_lower: bool
    ) -> float:
        score = payload.best_score
        if score is None:
            return float("inf") if prefers_lower else float("-inf")
        return score

    def _build_unique_results(
        self,
        unique_hits: dict[tuple[str | None, str | None, str], _UniqueHit],
        prefers_lower: bool,
    ) -> list[SearchUniqueResultPayload]:
        unique_payloads: list[SearchUniqueResultPayload] = []
        for hit in unique_hits.values():
            if not hit.matches:
                continue
            sorted_matches = self._sort_matches(hit.matches, prefers_lower)
            best_score = sorted_matches[0][1] if sorted_matches else None
            metadata_payload = normalize_metadata_for_output(hit.doc.metadata)
            metadata_payload.pop("matched_queries", None)
            unique_payloads.append(
                SearchUniqueResultPayload(
                    content=(hit.doc.page_content or "")[:500],
                    metadata=metadata_payload,
                    matched_queries=[
                        SearchMatchPayload(
                            query=query,
                            score=self._round_score(float(score)) or 0.0,
                        )
                        for query, score in sorted_matches
                    ],
                    best_score=self._round_score(best_score),
                )
            )

        unique_payloads.sort(
            key=lambda payload: self._unique_sort_key(payload, prefers_lower),
            reverse=not prefers_lower,
        )
        return unique_payloads

    @staticmethod
    def _build_metadata_filters_payload(filters: MetadataFilters) -> JsonDict:
        payload: JsonDict = {}
        for key, values in filters.items():
            cleaned: list[JsonValue] = []
            for value in values:
                if value != "":
                    cleaned.append(value)
            if cleaned:
                payload[str(key)] = cleaned
        return payload

    # metadata normalization now handled by normalize_metadata_for_output
