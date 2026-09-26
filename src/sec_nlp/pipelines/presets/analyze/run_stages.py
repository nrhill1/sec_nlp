# src/sec_nlp/pipelines/presets/analyze/run_stages.py
"""Ordered specialist steps for analyze pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field
from rich.progress import Progress, TaskID

from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines.base.stages import PipelineStage, StageSequence
from sec_nlp.pipelines.runtime.metadata import get_accession_from_metadata
from sec_nlp.pipelines.types import AnalysisResultDict, MetadataRecord
from sec_nlp.types import JsonDict

from .market import MarketEnrichment
from .types import (
    ChunkStats,
    PrefetchedSymbolData,
    Timings,
)

if TYPE_CHECKING:
    from .pipeline import AnalyzePipeline


@dataclass(slots=True)
class AnalyzeRunState:
    """In-place state carrier for analyze stages from document load through output write."""

    runtime: AnalyzePipeline
    symbol: str
    progress: Progress | None
    phase_task: TaskID | None
    prefetched: PrefetchedSymbolData | None = None
    timings: Timings = field(default_factory=dict)
    docs: list[Document] = field(default_factory=list)
    already_preprocessed: bool = False
    done: bool = False
    search_queries: list[str] | None = None
    stats: ChunkStats = field(default_factory=dict)
    filing_meta: MetadataRecord = field(default_factory=dict)
    processed_accessions: list[str] = field(default_factory=list)
    chunk_counts_by_accession: dict[str, int] = field(default_factory=dict)
    market_data: MarketEnrichment | None = None
    market_context: str | None = None
    analysis_results: list[AnalysisResultDict] = field(default_factory=list)
    relevant_results: list[AnalysisResultDict] = field(default_factory=list)
    market_correlation: JsonDict | None = None
    output_files: list[Path] = field(default_factory=list)


def _accession_from_doc(doc: Document) -> str | None:
    """Return accession number from a document metadata record."""
    return get_accession_from_metadata(doc.metadata)


def _summarize_loaded_docs(
    docs: list[Document],
) -> tuple[MetadataRecord, list[str], dict[str, int]]:
    """Return compact filing metadata needed after indexing completes."""
    fallback_meta: MetadataRecord = {}
    chunk_counts_by_accession: dict[str, int] = {}

    for doc in docs:
        metadata = doc.metadata or {}
        if not fallback_meta and metadata:
            fallback_meta = dict(metadata)
        accession = _accession_from_doc(doc)
        if accession is None:
            continue
        chunk_counts_by_accession[accession] = (
            chunk_counts_by_accession.get(accession, 0) + 1
        )

    return (
        fallback_meta,
        list(chunk_counts_by_accession),
        chunk_counts_by_accession,
    )


class LoadDocsStage(PipelineStage[AnalyzeRunState]):
    """Ingress stage that acquires candidate documents from prefetch or live retrieval."""

    name: str = Field(default="load_docs")

    def _run(self, state: AnalyzeRunState) -> AnalyzeRunState:
        """Execute the load docs stage and return updated run state."""
        logger.info("\n" + "=" * 70)
        logger.info("Processing symbol: %s", state.symbol)

        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Loading",
        )
        if state.prefetched is not None:
            state.docs = state.prefetched["docs"]
            state.timings.update(state.prefetched["timings"])
            state.already_preprocessed = state.prefetched["preprocessed"]
            state.runtime._record_symbol_discovery(
                symbol=state.symbol,
                efts_results=state.prefetched["efts_results"],
                efts_ok=state.prefetched["efts_ok"],
                relationships=state.prefetched["relationships"],
            )
            state.prefetched = None
        else:
            (
                state.docs,
                efts_results,
                efts_ok,
                relationships,
            ) = state.runtime._load_symbol_documents(
                state.symbol,
                state.timings,
            )
            state.runtime._record_symbol_discovery(
                symbol=state.symbol,
                efts_results=efts_results,
                efts_ok=efts_ok,
                relationships=relationships,
            )
        if state.docs:
            return state
        state.stats = state.runtime._empty_chunk_stats(state.timings)
        state.done = True
        return state


class PreprocessStage(PipelineStage[AnalyzeRunState]):
    """Normalization stage that converts loaded filings into analysis-ready chunks."""

    name: str = Field(default="preprocess_docs")

    def _run(self, state: AnalyzeRunState) -> AnalyzeRunState:
        """Execute the preprocess stage and return updated run state."""
        if state.done:
            return state
        if state.already_preprocessed:
            return state

        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Preprocessing",
        )
        state.docs = state.runtime._preprocess_documents(
            state.symbol,
            state.docs,
            state.timings,
        )
        if state.docs:
            return state
        state.stats = state.runtime._empty_chunk_stats(state.timings)
        state.done = True
        return state


class EnrichAndIndexStage(PipelineStage[AnalyzeRunState]):
    """Enrichment stage that adds market context and indexes chunks for retrieval."""

    name: str = Field(default="enrich_and_index")

    def _run(self, state: AnalyzeRunState) -> AnalyzeRunState:
        """Execute the enrich and index stage and return updated run state."""
        if state.done:
            return state
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Indexing",
        )
        state.stats, state.market_data, state.market_context = (
            state.runtime._enrich_and_index(
                state.symbol,
                state.docs,
                state.timings,
            )
        )
        (
            state.filing_meta,
            state.processed_accessions,
            state.chunk_counts_by_accession,
        ) = _summarize_loaded_docs(state.docs)
        state.docs = []
        return state


class SearchAndAnalyzeStage(PipelineStage[AnalyzeRunState]):
    """Inference stage that executes search queries and optional LLM analysis."""

    name: str = Field(default="search_and_analyze")

    def _run(self, state: AnalyzeRunState) -> AnalyzeRunState:
        """Execute the search and analyze stage and return updated run state."""
        if state.done:
            return state
        state.search_queries = state.runtime.config.get_search_queries()
        state.analysis_results, _ = state.runtime._run_search_and_analysis(
            state.symbol,
            state.search_queries,
            state.timings,
            progress=state.progress,
            phase_task=state.phase_task,
        )
        state.stats["analyzed_count"] = len(state.analysis_results)

        if state.runtime.config.search.analyze:
            return state
        logger.info(
            "Analysis disabled for %s (--search.analyze=false); exporting search results only",
            state.symbol,
        )
        state.timings["total"] = sum(state.timings.values())
        state.done = True
        return state


class PostprocessStage(PipelineStage[AnalyzeRunState]):
    """Reduction stage that filters findings and computes market-correlation overlays."""

    name: str = Field(default="postprocess_results")

    def _run(self, state: AnalyzeRunState) -> AnalyzeRunState:
        """Execute the postprocess stage and return updated run state."""
        if state.done:
            return state
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Post-processing",
        )
        (
            state.relevant_results,
            state.market_correlation,
        ) = state.runtime._postprocess_results(
            state.symbol,
            state.analysis_results,
            state.market_data,
        )
        return state


class WriteOutputsStage(PipelineStage[AnalyzeRunState]):
    """Egress stage that writes analysis artifacts and finalizes timing metadata."""

    name: str = Field(default="write_outputs")

    def _run(self, state: AnalyzeRunState) -> AnalyzeRunState:
        """Execute the write outputs stage and return updated run state."""
        if state.done:
            return state
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Writing",
        )
        state.output_files = state.runtime._write_symbol_outputs(
            symbol=state.symbol,
            filing_meta=state.filing_meta,
            analysis_results=state.analysis_results,
            relevant_results=state.relevant_results,
            search_queries=state.search_queries,
            timings=state.timings,
            market_data=state.market_data,
            market_context=state.market_context,
            market_correlation=state.market_correlation,
        )
        state.timings["total"] = sum(state.timings.values())

        processing_state = state.runtime._processing_state
        if processing_state is not None and state.processed_accessions:
            processing_state.mark_processed_batch(
                symbol=state.symbol,
                accessions=state.processed_accessions,
                run_id=state.runtime.config.run_id,
                chunk_counts=state.chunk_counts_by_accession,
            )

        state.analysis_results = []
        state.relevant_results = []
        state.market_data = None
        state.market_context = None
        state.market_correlation = None
        state.filing_meta = {}
        state.chunk_counts_by_accession = {}
        state.processed_accessions = []
        state.search_queries = None
        return state


_ANALYZE_STAGES: tuple[PipelineStage[AnalyzeRunState], ...] = (
    LoadDocsStage(),
    PreprocessStage(),
    EnrichAndIndexStage(),
    SearchAndAnalyzeStage(),
    PostprocessStage(),
    WriteOutputsStage(),
)


def build_analyze_stage_chain(
    pipeline: AnalyzePipeline,
) -> StageSequence[AnalyzeRunState]:
    """Build deterministic analyze stage chain."""
    return pipeline.build_configured_stage_chain(stages=_ANALYZE_STAGES)
