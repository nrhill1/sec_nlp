# src/sec_nlp/pipelines/presets/analyze/steps/search/vector_search.py
"""Vector search utilities for the analyze pipeline."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_core.runnables import RunnableConfig, RunnableSerializable
from langchain_qdrant import QdrantVectorStore
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.infra.logger import log_divider, logger
from sec_nlp.pipelines.metadata.filters import (
    MetadataFilters,
    build_metadata_filter,
)
from sec_nlp.pipelines.output_io import write_yaml
from sec_nlp.pipelines.types import (
    MetadataMap,
    MetadataValue,
)
from sec_nlp.types import JsonDict, JsonValue

from ...config import AnalyzeConfig
from ...utils import query_term_overlap, resolve_symbol_for_output
from ..analysis.analysis_runner import AnalysisBatchInput
from .payloads import (
    SearchHighlightsPayload,
    SearchMatchPayload,
    SearchQuerySectionPayload,
    SearchResultPayload,
    SearchStatsPayload,
    SearchSummaryPayload,
    SearchUniqueResultPayload,
)


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

    config: AnalyzeConfig = Field(description="Analyze pipeline config")
    vector_store: QdrantVectorStore | None = Field(
        default=None, description="Vector store backend"
    )

    def invoke(
        self,
        input: SearchRetrieveInput,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> AnalysisBatchInput:
        """Invoke the runnable for chaining in a sequence."""
        _ = config
        _ = kwargs
        queries = input.queries
        docs = self.retrieve_hits(queries)
        fallback_symbol = input.symbol or (
            self.config.symbols[0] if self.config.symbols else "<unknown>"
        )
        return AnalysisBatchInput(symbol=fallback_symbol, docs=docs)

    def search_queries(
        self, queries: list[str] | None = None
    ) -> SearchResultsByQuery:
        """Run similarity search per query and return filtered hits."""
        query_list = (
            self.config.get_search_queries() if queries is None else queries
        )
        query_list = self._clean_queries(query_list)
        if (
            not self.vector_store
            or not query_list
            or self.config.vector_mode == "off"
        ):
            return {}

        distance_metric = self.config.vdb.qdrant_distance
        distance_prefers_lower = distance_metric in ("Cosine", "Euclid")
        threshold = self.config.search.score_threshold
        metadata_filter = build_metadata_filter(
            self.config.search.metadata_filters
        )
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
            results = self.vector_store.similarity_search_with_score(
                query,
                k=self.config.search.limit,
                filter=metadata_filter,
            )
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

        distance_metric = self.config.vdb.qdrant_distance
        distance_prefers_lower = distance_metric in ("Cosine", "Euclid")

        unique_hits: dict[tuple[str, str | None, str | None], _UniqueHit] = {}

        for query, query_results in results_by_query.items():
            for doc, score in query_results.filtered:
                meta = doc.metadata or {}
                key = (
                    doc.page_content or "",
                    meta.get("section_number"),
                    meta.get("symbol"),
                )
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
        min_hits = self.config.search.query_term_min_hits
        min_ratio = self.config.search.query_term_min_ratio
        min_len = self.config.search.query_term_min_len
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

    def run(self, queries: list[str] | None = None) -> list[Path]:
        """Run semantic search queries if configured."""
        query_list = (
            self.config.get_search_queries() if queries is None else queries
        )
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
        if self.config.search.analyze:
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
        query_list = (
            self.config.get_search_queries() if queries is None else queries
        )
        query_list = self._clean_queries(query_list)
        if not query_list:
            logger.warning(
                "Search not configured: no queries or topics provided"
            )
            return []
        if not self.config.search.export_results:
            logger.info("Search export disabled; skipping results export")
            return []

        if cached:
            logger.info("Reusing cached search results for export")

        log_divider(logger, color="yellow")
        logger.info(
            "Exporting results for %d semantic search queries",
            len(query_list),
        )

        distance_metric = self.config.vdb.qdrant_distance
        distance_prefers_lower = distance_metric in ("Cosine", "Euclid")
        threshold = self.config.search.score_threshold
        metadata_filters_payload = self._build_metadata_filters_payload(
            self.config.search.metadata_filters
        )

        per_symbol_query_results: dict[
            str, dict[str, list[tuple[Document, float]]]
        ] = defaultdict(lambda: defaultdict(list))
        unique_hits: dict[
            str, dict[tuple[str, str | None, str], _UniqueHit]
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
                        self.config.symbols[0]
                        if self.config.symbols
                        else "<unknown>",
                        meta,
                    )
                    per_symbol_query_results[symbol_for_output][query].append(
                        (doc, score)
                    )

                    key = (
                        doc.page_content or "",
                        meta.get("section_number"),
                        symbol_for_output,
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
            output_dir = (
                self.config.get_symbol_output_dir(symbol_key) / "search"
            )
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
                        score=float(score),
                        content=(doc.page_content or "")[:500],
                        metadata=(
                            metadata_payload := self._normalize_metadata(
                                doc.metadata
                            )
                        ),
                        summary=metadata_payload.get("summary"),
                        tags=metadata_payload.get("tags"),
                        sentiment=metadata_payload.get("sentiment"),
                        forward_looking=self._coerce_bool(
                            metadata_payload.get("forward_looking")
                        ),
                        confidence_score=self._coerce_float(
                            metadata_payload.get("confidence_score")
                        ),
                    )
                    for doc, score in symbol_results
                ]

                stats_payload = SearchStatsPayload(
                    average_score=avg_score,
                    best_score=best_score,
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
        unique_hits: dict[tuple[str, str | None, str], _UniqueHit],
        prefers_lower: bool,
    ) -> list[SearchUniqueResultPayload]:
        unique_payloads: list[SearchUniqueResultPayload] = []
        for hit in unique_hits.values():
            if not hit.matches:
                continue
            sorted_matches = self._sort_matches(hit.matches, prefers_lower)
            best_score = sorted_matches[0][1] if sorted_matches else None
            metadata_payload = self._normalize_metadata(hit.doc.metadata)
            metadata_payload.pop("matched_queries", None)
            unique_payloads.append(
                SearchUniqueResultPayload(
                    content=(hit.doc.page_content or "")[:500],
                    metadata=metadata_payload,
                    matched_queries=[
                        SearchMatchPayload(query=query, score=float(score))
                        for query, score in sorted_matches
                    ],
                    best_score=best_score,
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

    @classmethod
    def _normalize_metadata(cls, metadata: MetadataMap | None) -> JsonDict:
        if not metadata:
            return {}
        payload: JsonDict = {}
        for key, raw_value in metadata.items():
            normalized = cls._normalize_metadata_value(raw_value)
            if normalized is not None:
                payload[str(key)] = normalized
        return payload

    @classmethod
    def _normalize_metadata_value(
        cls, value: MetadataValue | Path
    ) -> JsonValue | None:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, dict):
            nested: JsonDict = {}
            for nested_key, nested_value in value.items():
                if not isinstance(nested_key, str):
                    continue
                normalized = cls._normalize_metadata_value(nested_value)
                if normalized is not None:
                    nested[nested_key] = normalized
            return nested or None
        if isinstance(value, list):
            items: list[JsonValue] = []
            for item in value:
                normalized = cls._normalize_metadata_value(item)
                if normalized is not None:
                    items.append(normalized)
            return items or None
        return None

    @staticmethod
    def _coerce_bool(value: JsonValue | None) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned in ("true", "false"):
                return cleaned == "true"
        return None

    @staticmethod
    def _coerce_float(value: JsonValue | None) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None
