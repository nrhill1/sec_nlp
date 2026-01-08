# src/sec_nlp/pipelines/presets/analyze/steps/analysis/analysis_runner.py
"""LLM analysis runner for analyze pipeline chunks."""

from __future__ import annotations

from typing import Any

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

from ...config import AnalyzeConfig
from ...models import AnalysisInput, AnalysisResult
from ...utils import resolve_symbol_for_output


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

    config: AnalyzeConfig = Field(description="Analyze pipeline config")
    graph: Runnable[AnalysisInput, AnalysisResult] = Field(
        description="Runnable LLM graph"
    )
    callbacks: list[BaseCallbackHandler] = Field(default_factory=list)
    analysis_instructions: str = Field(default="")

    def invoke(
        self,
        input: AnalysisBatchInput,
        config: RunnableConfig | None = None,
        **kwargs: Any,
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
            matched_query_value = (
                str(matched_queries[0].get("query"))
                if matched_queries
                and isinstance(matched_queries[0], dict)
                and matched_queries[0].get("query")
                else None
            )
            inputs.append(
                AnalysisInput(
                    symbol=doc_symbol,
                    chunk=doc.page_content,
                    matched_query=matched_query_value,
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
            for i in range(0, len(inputs), self.config.batch_size):
                batch = inputs[i : i + self.config.batch_size]
                batch_docs = docs[i : i + self.config.batch_size]
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
                else self.config.symbols[0]
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

        config_callbacks: RunnableConfig | None = (
            RunnableConfig(callbacks=self.callbacks) if self.callbacks else None
        )

        attempts = self.config.llm_retry_attempts + 1
        backoff = self.config.llm_retry_backoff

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
                    import time

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
            config_callbacks: RunnableConfig | None = None
            if self.callbacks:
                config_callbacks = RunnableConfig(callbacks=self.callbacks)
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

        return " | ".join(context_parts) if context_parts else None

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
        for key in ("matched_queries", "search_query", "search_score"):
            source_metadata.pop(key, None)
        result_dict: AnalysisResultDict = {
            "is_relevant": result.is_relevant,
            "confidence_score": result.confidence_score,
            "summary": result.summary,
            "key_points": result.key_points,
            "reasoning": result.reasoning,
            "extracted_entities": result.extracted_entities,
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

        if self.config.include_raw_chunks:
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
            **(
                {"raw_chunk": item.chunk}
                if self.config.include_raw_chunks
                else {}
            ),
        }
