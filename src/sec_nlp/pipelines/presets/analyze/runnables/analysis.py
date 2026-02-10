# src/sec_nlp/pipelines/presets/analyze/runnables/analysis.py
"""LLM analysis runner for analyze pipeline chunks."""

from __future__ import annotations

import asyncio
import re
import time
from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.documents import Document
from langchain_core.runnables import (
    Runnable,
    RunnableConfig,
    RunnableSerializable,
)
from pydantic import BaseModel, ConfigDict, Field
from tqdm import tqdm

from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines.metadata.accession import get_accession_from_metadata
from sec_nlp.pipelines.types import AnalysisResultDict, MetadataRecord
from sec_nlp.types import JsonValue

from ..models import AnalysisInput, AnalysisResult
from ..utils import query_term_overlap, resolve_symbol_for_output

NUMERIC_SIGNAL_RE = re.compile(r"[$€£]?\d")


class AnalysisBatchInput(BaseModel):
    """Runnable input for analyzing a batch of documents."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    symbol: str
    docs: list[Document]


class AnalyzerRunnable(
    RunnableSerializable[AnalysisBatchInput, list[AnalysisResultDict]]
):
    """Run LLM analysis over prepared document chunks."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    graph: Runnable[AnalysisInput, AnalysisResult] = Field(
        description="Runnable LLM graph"
    )
    callbacks: list[BaseCallbackHandler] = Field(default_factory=list)
    analysis_instructions: str = Field(default="")
    symbols: list[str] = Field(default_factory=list)
    llm_retry_attempts: int = Field(default=0, ge=0)
    llm_retry_backoff: float = Field(default=0.0, ge=0.0)
    confidence_mode: str = Field(default="basic")
    include_raw_chunks: bool = Field(default=False)
    batch_size: int = Field(default=8, ge=1)
    query_term_min_len: int = Field(default=3, ge=1)
    run_id: UUID | None = None

    def invoke(
        self,
        input: AnalysisBatchInput,
        config: RunnableConfig | None = None,
        **kwargs: JsonValue,
    ) -> list[AnalysisResultDict]:
        """Invoke the runnable for chaining in a sequence."""
        _ = config
        _ = kwargs
        if not input.docs:
            return []
        return self.analyze_chunks(input.symbol, input.docs)

    def analyze_chunks(
        self, symbol: str, docs: list[Document]
    ) -> list[AnalysisResultDict]:
        """Analyze document chunks using the LLM graph."""
        if len(docs) == 0:
            raise ValueError("Cannot analyze empty docs list")

        inputs: list[AnalysisInput] = []
        for doc in docs:
            metadata = doc.metadata or {}
            doc_symbol = resolve_symbol_for_output(symbol, metadata)
            matched_queries = self._extract_matched_queries(metadata)
            matched_query_value = self._select_primary_query(
                matched_queries, doc.page_content
            )
            matched_query_list = self._build_matched_query_list(matched_queries)
            inputs.append(
                AnalysisInput(
                    symbol=doc_symbol,
                    chunk=doc.page_content,
                    matched_query=matched_query_value,
                    matched_queries=matched_query_list,
                    context=self._build_context(doc),
                    topic_hits=metadata.get("topic_hits"),
                    analysis_instructions=self.analysis_instructions,
                )
            )

        results: list[AnalysisResultDict] = []

        bar_format = (
            "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining},"
            " {rate_fmt}]"
        )
        with tqdm(
            total=len(inputs),
            desc=f"Analyzing content for {symbol}",
            unit="chunk",
            colour="cyan",
            leave=False,
            bar_format=bar_format,
        ) as pbar:
            for i in range(0, len(inputs), self.batch_size):
                batch = inputs[i : i + self.batch_size]
                batch_docs = docs[i : i + self.batch_size]
                batch_results = self._process_batch(batch, batch_docs)
                results.extend(batch_results)
                pbar.update(len(batch))
                pbar.set_postfix({"last_batch": len(batch)})

        return results

    def analyze_search_hits(
        self,
        query: str,
        results: list[tuple[Document, float]],
    ) -> list[AnalysisResultDict]:
        """Run LLM analysis on search hits (limited subset)."""
        if not results:
            return []

        docs: list[Document] = []
        inputs: list[AnalysisInput] = []

        for doc, score in results:
            meta = doc.metadata or {}
            meta = {
                **meta,
                "matched_queries": [
                    {"query": query, "score": float(score)},
                ],
            }
            doc.metadata = meta
            symbol_value = meta.get("symbol")
            symbol = (
                symbol_value
                if isinstance(symbol_value, str) and symbol_value
                else (self.symbols[0] if self.symbols else "<unknown>")
            )
            topic_hits_value = meta.get("topic_hits")
            topic_hits = (
                [str(hit) for hit in topic_hits_value]
                if isinstance(topic_hits_value, list)
                else None
            )
            inputs.append(
                AnalysisInput(
                    symbol=symbol,
                    chunk=doc.page_content,
                    matched_query=query,
                    matched_queries=[query],
                    context=self._build_context(doc),
                    topic_hits=topic_hits,
                    analysis_instructions=self.analysis_instructions,
                )
            )
            docs.append(doc)

        return self._process_batch(inputs, docs)

    def _process_batch(
        self, batch: list[AnalysisInput], docs: list[Document]
    ) -> list[AnalysisResultDict]:
        """Process a batch with fallback to individual processing."""
        if not batch:
            raise ValueError("Cannot process empty batch")
        if len(batch) != len(docs):
            raise ValueError(
                f"Batch size mismatch: {len(batch)} inputs vs {len(docs)} docs"
            )

        config_callbacks = self._build_runnable_config(include_run_id=False)

        attempts = self.llm_retry_attempts + 1
        backoff = self.llm_retry_backoff

        for attempt in range(attempts):
            try:
                results: list[AnalysisResult] = self.graph.batch(
                    batch, config=config_callbacks
                )
                formatted_results: list[AnalysisResultDict] = []

                for result, doc in zip(results, docs, strict=True):
                    formatted_results.append(self._format_result(result, doc))

                return formatted_results
            except Exception as e:
                if attempt < attempts - 1:
                    logger.warning(
                        "Batch processing failed (attempt %d/%d): %s. Retrying after %.1fs...",
                        attempt + 1,
                        attempts,
                        e,
                        backoff,
                    )
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None
                    if loop is not None and loop.is_running():
                        # Inside an async context — yield to the event loop
                        import concurrent.futures

                        with concurrent.futures.ThreadPoolExecutor(
                            max_workers=1
                        ) as pool:
                            loop.run_in_executor(pool, time.sleep, backoff)
                    else:
                        time.sleep(backoff)
                    backoff *= 2
                    continue
                logger.warning(
                    "Batch processing failed after %d attempts: %s. Processing items individually...",
                    attempts,
                    e,
                )
                return [
                    self._process_single_item(item, doc)
                    for item, doc in zip(batch, docs, strict=True)
                ]
        return []

    def _process_single_item(
        self, item: AnalysisInput, doc: Document
    ) -> AnalysisResultDict:
        """Process a single item."""
        try:
            config_callbacks = self._build_runnable_config(include_run_id=True)
            result: AnalysisResult = self.graph.invoke(
                item, config=config_callbacks
            )
            return self._format_result(result, doc)

        except Exception as e:
            logger.error("Item processing failed: %s", e)
            return self._create_error_result(item, doc, e)

    @staticmethod
    def _build_context(doc: Document) -> str | None:
        """Assemble contextual hints for the LLM."""
        context_parts: list[str] = []
        section = (doc.metadata or {}).get("section_number")
        if section:
            context_parts.append(f"section: {section}")

        topic_hits = (doc.metadata or {}).get("topic_hits")
        if topic_hits:
            context_parts.append("topics: " + ", ".join(topic_hits[:5]))

        market_hint = (doc.metadata or {}).get("market_enrichment_context")
        if isinstance(market_hint, str) and market_hint:
            context_parts.append(market_hint)

        return " | ".join(context_parts) if context_parts else None

    @staticmethod
    def _build_matched_query_list(
        matched_queries: list[dict[str, float | str]],
    ) -> list[str] | None:
        queries: list[str] = []
        seen: set[str] = set()
        for item in matched_queries:
            query = item.get("query")
            if not isinstance(query, str):
                continue
            cleaned = query.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            queries.append(cleaned)
            if len(queries) >= 3:
                break
        return queries or None

    def _select_primary_query(
        self,
        matched_queries: list[dict[str, float | str]],
        content: str | None,
    ) -> str | None:
        if not matched_queries:
            return None
        best_query: str | None = None
        best_ratio = -1.0
        for item in matched_queries:
            query = item.get("query")
            if not isinstance(query, str):
                continue
            cleaned = query.strip()
            if not cleaned:
                continue
            _, _, ratio = query_term_overlap(
                cleaned,
                content,
                min_len=self.query_term_min_len,
            )
            if ratio > best_ratio:
                best_ratio = ratio
                best_query = cleaned
        if best_query is not None:
            return best_query
        first_query = matched_queries[0].get("query")
        return (
            str(first_query).strip()
            if isinstance(first_query, str) and first_query.strip()
            else None
        )

    @classmethod
    def _has_numeric_signal(cls, *values: str | None) -> bool:
        for value in values:
            if value and NUMERIC_SIGNAL_RE.search(value):
                return True
        return False

    def _calibrate_confidence(
        self,
        *,
        llm_confidence: float | None,
        is_relevant: bool,
        matched_terms: list[str],
        missing_terms: list[str],
        overlap_ratio: float,
        result: AnalysisResult,
    ) -> float | None:
        if llm_confidence is None and not matched_terms and not missing_terms:
            return None

        score = 0.2 + (0.6 * overlap_ratio)
        if result.source_excerpt or result.evidence_spans:
            score += 0.1
        key_points = "; ".join(result.key_points or []) or None
        if self._has_numeric_signal(result.summary, key_points):
            score += 0.1
        if result.binding_status == "binding":
            score += 0.05
        elif result.binding_status == "non_binding":
            score -= 0.05
        if missing_terms:
            score -= 0.15
        if not is_relevant:
            score = min(score, 0.4)
        score = max(0.05, min(score, 0.99))
        return score

    @staticmethod
    def _extract_matched_queries(
        metadata: MetadataRecord | None,
    ) -> list[dict[str, float | str]]:
        raw_matches = (metadata or {}).get("matched_queries")
        if isinstance(raw_matches, list):
            cleaned: list[dict[str, float | str]] = []
            for item in raw_matches:
                if not isinstance(item, dict):
                    continue
                query = item.get("query")
                score = item.get("score")
                if not isinstance(query, str) or not query.strip():
                    continue
                payload: dict[str, float | str] = {"query": query.strip()}
                if isinstance(score, (int, float)):
                    payload["score"] = float(score)
                cleaned.append(payload)
            return cleaned

        query = (metadata or {}).get("search_query")
        if isinstance(query, str) and query.strip():
            payload: dict[str, float | str] = {"query": query.strip()}
            score = (metadata or {}).get("search_score")
            if isinstance(score, (int, float)):
                payload["score"] = float(score)
            return [payload]
        return []

    def _format_result(
        self, result: AnalysisResult, doc: Document
    ) -> AnalysisResultDict:
        source_metadata: MetadataRecord = {
            **(doc.metadata or {}),
            "accession_number": get_accession_from_metadata(doc.metadata),
        }
        matched_queries = self._extract_matched_queries(source_metadata)
        primary_query = self._select_primary_query(
            matched_queries, doc.page_content
        )
        query_match_terms, missing_query_terms, overlap_ratio = (
            query_term_overlap(
                primary_query,
                doc.page_content,
                min_len=self.query_term_min_len,
            )
        )
        for key in ("matched_queries", "search_query", "search_score"):
            source_metadata.pop(key, None)
        is_relevant = result.is_relevant
        if primary_query and not query_match_terms and is_relevant:
            is_relevant = False

        confidence_score = result.confidence_score
        if self.confidence_mode == "calibrated":
            calibrated = self._calibrate_confidence(
                llm_confidence=confidence_score,
                is_relevant=is_relevant,
                matched_terms=query_match_terms,
                missing_terms=missing_query_terms,
                overlap_ratio=overlap_ratio,
                result=result,
            )
            if calibrated is not None:
                if confidence_score is None:
                    confidence_score = calibrated
                else:
                    confidence_score = min(float(confidence_score), calibrated)

        result_dict: AnalysisResultDict = {
            "is_relevant": is_relevant,
            "confidence_score": confidence_score,
            "summary": result.summary,
            "key_points": result.key_points,
            "reasoning": result.reasoning,
            "query_match_terms": query_match_terms,
            "missing_query_terms": missing_query_terms,
            "binding_status": result.binding_status,
            "contingencies": result.contingencies,
            "impact_channels": result.impact_channels,
            "impact_direction": result.impact_direction,
            "impact_magnitude": result.impact_magnitude,
            "impact_horizon": result.impact_horizon,
            "impact_confidence": result.impact_confidence,
            "impact_rationale": result.impact_rationale,
            "extracted_entities": result.extracted_entities,
            "compensation_data": result.compensation_data,
            "proposal_info": result.proposal_info,
            "performance_metrics": result.performance_metrics,
            "peer_set": result.peer_set,
            "pay_for_performance_flags": result.pay_for_performance_flags,
            "tags": result.tags,
            "evidence_spans": result.evidence_spans,
            "source_excerpt": result.source_excerpt,
            "severity": result.severity,
            "sentiment": result.sentiment,
            "forward_looking": result.forward_looking,
            "follow_up_questions": result.follow_up_questions,
            "source_metadata": source_metadata,
        }
        if matched_queries:
            result_dict["matched_queries"] = matched_queries

        if self.include_raw_chunks:
            result_dict["raw_chunk"] = doc.page_content

        return result_dict

    def _create_error_result(
        self, item: AnalysisInput, doc: Document, error: Exception
    ) -> AnalysisResultDict:
        """Create an error result dict for a failed item."""
        chunk_preview = (
            item.chunk[:100] + "..." if len(item.chunk) > 100 else item.chunk
        )

        source_metadata: MetadataRecord = {
            **(doc.metadata or {}),
            "accession_number": get_accession_from_metadata(doc.metadata),
        }
        matched_queries = self._extract_matched_queries(source_metadata)
        for key in ("matched_queries", "search_query", "search_score"):
            source_metadata.pop(key, None)
        return {
            "error": "Processing failed",
            "exception": f"{type(error).__name__}: {error}",
            "chunk_preview": chunk_preview,
            "source_metadata": source_metadata,
            **({"matched_queries": matched_queries} if matched_queries else {}),
            **({"raw_chunk": item.chunk} if self.include_raw_chunks else {}),
        }

    def _build_runnable_config(
        self, *, include_run_id: bool
    ) -> RunnableConfig | None:
        config: RunnableConfig = {}
        if self.callbacks:
            config["callbacks"] = self.callbacks
        if self.run_id is not None:
            config["metadata"] = {"pipeline_run_id": str(self.run_id)}
            if include_run_id:
                config["run_id"] = self.run_id
        return config or None
