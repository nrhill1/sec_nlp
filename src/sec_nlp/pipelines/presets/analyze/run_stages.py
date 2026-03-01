# src/sec_nlp/pipelines/presets/analyze/run_stages.py
"""Runnable stage helpers for analyze pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.documents import Document
from langchain_core.runnables import Runnable
from pydantic import Field
from rich.progress import Progress, TaskID

from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines.base.stages import PipelineStageRunnable
from sec_nlp.pipelines.metadata.accession import get_accession_from_metadata
from sec_nlp.pipelines.types import AnalysisResultDict
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
    """Mutable in-process state shared across analyze runnable stages."""

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
    market_data: MarketEnrichment | None = None
    market_context: str | None = None
    analysis_results: list[AnalysisResultDict] = field(default_factory=list)
    docs_for_analysis: list[Document] = field(default_factory=list)
    relevant_results: list[AnalysisResultDict] = field(default_factory=list)
    market_correlation: JsonDict | None = None
    output_files: list[Path] = field(default_factory=list)


def _accession_from_doc(doc: Document) -> str | None:
    """Return accession number from a document metadata record."""
    return get_accession_from_metadata(doc.metadata)


def create_initial_analyze_state(
    *,
    symbol: str,
    progress: Progress | None,
    phase_task: TaskID | None,
    prefetched: PrefetchedSymbolData | None,
) -> AnalyzeRunState:
    """Create initial mutable state for analyze runnable stage execution."""
    return AnalyzeRunState(
        symbol=symbol,
        progress=progress,
        phase_task=phase_task,
        prefetched=prefetched,
    )


class LoadDocsStage(PipelineStageRunnable[AnalyzeRunState]):
    """Load candidate documents using prefetch or live retrieval."""

    pipeline: AnalyzePipeline = Field(exclude=True, repr=False)
    name: str = Field(default="load_docs")

    def _run(self, state: AnalyzeRunState) -> AnalyzeRunState:
        """Execute the load docs stage and return updated run state."""
        logger.info("\n" + "=" * 70)
        logger.info("Processing symbol: %s", state.symbol)

        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Loading",
        )
        if state.prefetched is not None:
            state.docs = state.prefetched["docs"]
            state.timings.update(state.prefetched["timings"])
            state.already_preprocessed = state.prefetched["preprocessed"]
        else:
            self.pipeline._loader.add_symbol(state.symbol)
            state.docs, _allowed = self.pipeline._run_efts_and_load_docs(
                state.symbol,
                state.timings,
            )
        if state.docs:
            return state
        state.stats = self.pipeline._empty_chunk_stats(state.timings)
        state.done = True
        return state


class PreprocessStage(PipelineStageRunnable[AnalyzeRunState]):
    """Preprocess loaded documents into analysis chunks."""

    pipeline: AnalyzePipeline = Field(exclude=True, repr=False)
    name: str = Field(default="preprocess_docs")

    def _run(self, state: AnalyzeRunState) -> AnalyzeRunState:
        """Execute the preprocess stage and return updated run state."""
        if state.done:
            return state
        if state.already_preprocessed:
            return state

        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Preprocessing",
        )
        state.docs = self.pipeline._preprocess_documents(
            state.symbol,
            state.docs,
            state.timings,
        )
        if state.docs:
            return state
        state.stats = self.pipeline._empty_chunk_stats(state.timings)
        state.done = True
        return state


class EnrichAndIndexStage(PipelineStageRunnable[AnalyzeRunState]):
    """Attach market context and index chunks into vector store."""

    pipeline: AnalyzePipeline = Field(exclude=True, repr=False)
    name: str = Field(default="enrich_and_index")

    def _run(self, state: AnalyzeRunState) -> AnalyzeRunState:
        """Execute the enrich and index stage and return updated run state."""
        if state.done:
            return state
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Indexing",
        )
        state.stats, state.market_data, state.market_context = (
            self.pipeline._enrich_and_index(
                state.symbol,
                state.docs,
                state.timings,
            )
        )
        return state


class SearchAndAnalyzeStage(PipelineStageRunnable[AnalyzeRunState]):
    """Run vector retrieval and optional LLM analysis."""

    pipeline: AnalyzePipeline = Field(exclude=True, repr=False)
    name: str = Field(default="search_and_analyze")

    def _run(self, state: AnalyzeRunState) -> AnalyzeRunState:
        """Execute the search and analyze stage and return updated run state."""
        if state.done:
            return state
        state.search_queries = self.pipeline.config.get_search_queries()
        (
            state.analysis_results,
            state.docs_for_analysis,
        ) = self.pipeline._run_search_and_analysis(
            state.symbol,
            state.search_queries,
            state.timings,
            progress=state.progress,
            phase_task=state.phase_task,
        )
        state.stats["analyzed_count"] = len(state.analysis_results)

        if self.pipeline.config.search.analyze:
            return state
        logger.info(
            "Analysis disabled for %s (--search.analyze=false); exporting search results only",
            state.symbol,
        )
        state.timings["total"] = sum(state.timings.values())
        state.done = True
        return state


class PostprocessStage(PipelineStageRunnable[AnalyzeRunState]):
    """Filter analysis outputs and compute market correlation."""

    pipeline: AnalyzePipeline = Field(exclude=True, repr=False)
    name: str = Field(default="postprocess_results")

    def _run(self, state: AnalyzeRunState) -> AnalyzeRunState:
        """Execute the postprocess stage and return updated run state."""
        if state.done:
            return state
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Post-processing",
        )
        (
            state.relevant_results,
            state.market_correlation,
        ) = self.pipeline._postprocess_results(
            state.symbol,
            state.analysis_results,
            state.market_data,
        )
        return state


class WriteOutputsStage(PipelineStageRunnable[AnalyzeRunState]):
    """Write analysis outputs and finalize timing metadata."""

    pipeline: AnalyzePipeline = Field(exclude=True, repr=False)
    name: str = Field(default="write_outputs")

    def _run(self, state: AnalyzeRunState) -> AnalyzeRunState:
        """Execute the write outputs stage and return updated run state."""
        if state.done:
            return state
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Writing",
        )
        state.output_files = self.pipeline._write_symbol_outputs(
            symbol=state.symbol,
            docs=state.docs,
            analysis_results=state.analysis_results,
            relevant_results=state.relevant_results,
            search_queries=state.search_queries,
            timings=state.timings,
            market_data=state.market_data,
            market_context=state.market_context,
            market_correlation=state.market_correlation,
        )
        state.timings["total"] = sum(state.timings.values())

        processing_state = self.pipeline._processing_state
        if processing_state is None or not state.docs:
            return state
        processed_accessions = list(
            {
                accession
                for accession in (
                    _accession_from_doc(doc) for doc in state.docs
                )
                if accession
            }
        )
        if not processed_accessions:
            return state
        processing_state.mark_processed_batch(
            symbol=state.symbol,
            accessions=processed_accessions,
            run_id=self.pipeline.config.run_id,
            chunk_counts={
                accession: sum(
                    1
                    for doc in state.docs
                    if _accession_from_doc(doc) == accession
                )
                for accession in processed_accessions
            },
        )
        return state


def build_analyze_stage_chain(
    pipeline: AnalyzePipeline,
) -> Runnable[AnalyzeRunState, AnalyzeRunState]:
    """Build deterministic analyze stage chain."""
    types_namespace = {"AnalyzePipeline": pipeline.__class__}
    LoadDocsStage.model_rebuild(_types_namespace=types_namespace, force=True)
    PreprocessStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    EnrichAndIndexStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    SearchAndAnalyzeStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    PostprocessStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    WriteOutputsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    stages: tuple[PipelineStageRunnable[AnalyzeRunState], ...] = (
        LoadDocsStage(pipeline=pipeline),
        PreprocessStage(pipeline=pipeline),
        EnrichAndIndexStage(pipeline=pipeline),
        SearchAndAnalyzeStage(pipeline=pipeline),
        PostprocessStage(pipeline=pipeline),
        WriteOutputsStage(pipeline=pipeline),
    )
    configured_stages = tuple(
        stage.configured(
            pipeline_type=pipeline.pipeline_type,
            run_id=str(pipeline.config.run_id),
        )
        for stage in stages
    )
    return pipeline.build_stage_chain(stages=configured_stages)
