# src/sec_nlp/pipelines/presets/exb/run_stages.py
"""Runnable stage helpers for exhibit pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.documents import Document
from langchain_core.runnables import Runnable
from pydantic import Field

from sec_nlp.core.infra.logger import log_divider, logger
from sec_nlp.core.text.keyword import KeywordMatcher
from sec_nlp.pipelines.base.stages import PipelineStageRunnable
from sec_nlp.pipelines.metadata.exhibit import prepare_vector_docs
from sec_nlp.pipelines.observability.telemetry import log_chunk_length_stats
from sec_nlp.pipelines.vector import upload_documents

from .io.exhibit_summary import write_exhibit_summary
from .io.outputs import write_exhibit_outputs
from .steps.extract.exhibits import ExhibitStats

if TYPE_CHECKING:
    from .pipeline import ExhibitPipeline


CONTRACT_KEYWORD_CATEGORY_TERMS = {
    "exclusivity": ["exclusive"],
    "cost": ["cost", "pricing", "cost-"],
    "aftermarket": [
        "aftermarket",
        "repair",
        "replacement",
        "maintenance",
        "service",
    ],
    "components": ["component", "engine", "part"],
    "supply": [
        "supplier",
        "supply",
        "offtake",
        "purchase",
        "distribution",
        "contract",
        "agreement",
        "schedule",
    ],
}


@dataclass(slots=True)
class ExhibitRunState:
    """Mutable in-process state shared across exhibit runnable stages."""

    symbol: str
    include_bridge: bool
    allowed_accessions: set[str] | None = None
    keyword_terms: list[str] = field(default_factory=list)
    keyword_categories: dict[str, list[str]] = field(default_factory=dict)
    exhibit_docs: list[Document] = field(default_factory=list)
    filtered_docs: list[Document] = field(default_factory=list)
    bridge_docs: list[Document] = field(default_factory=list)
    output_files: list[Path] = field(default_factory=list)
    stats: ExhibitStats = field(default_factory=ExhibitStats)
    skip_symbol: bool = False
    done: bool = False


def create_initial_exhibit_state(
    *,
    symbol: str,
    include_bridge: bool,
) -> ExhibitRunState:
    """Create initial mutable state for exhibit runnable stage execution."""
    return ExhibitRunState(
        symbol=symbol,
        include_bridge=include_bridge,
    )


class CandidateAccessionsStage(PipelineStageRunnable[ExhibitRunState]):
    """Apply candidate-first accession narrowing when enabled."""

    pipeline: ExhibitPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="candidate_accessions")

    def _run(self, state: ExhibitRunState) -> ExhibitRunState:
        log_divider(logger, color="cyan")
        logger.info("Processing symbol: %s \n", state.symbol)

        if not (
            self.pipeline.config.candidate_first
            and self.pipeline.config.has_contract_exhibits()
        ):
            return state

        state.allowed_accessions = self.pipeline._build_candidate_accessions(
            state.symbol
        )
        if state.allowed_accessions:
            logger.info(
                "Candidate-first narrowed %s to %d accessions",
                state.symbol,
                len(state.allowed_accessions),
            )
            return state

        if self.pipeline.config.candidate_fallback_full_scan:
            logger.warning(
                "Candidate-first found no accessions for %s; falling back to full scan",
                state.symbol,
            )
            state.allowed_accessions = None
            return state

        logger.warning(
            "Candidate-first found no accessions for %s; skipping symbol",
            state.symbol,
        )
        state.skip_symbol = True
        state.done = True
        return state


class CollectExhibitDocsStage(PipelineStageRunnable[ExhibitRunState]):
    """Collect exhibit chunks from filings."""

    pipeline: ExhibitPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="collect_exhibit_docs")

    def _run(self, state: ExhibitRunState) -> ExhibitRunState:
        if state.done:
            return state

        self.pipeline._loader.add_symbol(state.symbol)
        if self.pipeline.config.has_contract_exhibits():
            state.keyword_terms = [
                term.lower()
                for term in self.pipeline.config.search_terms
                if term
            ]
        state.keyword_categories = KeywordMatcher.build_keyword_categories(
            state.keyword_terms,
            category_terms=CONTRACT_KEYWORD_CATEGORY_TERMS,
        )

        state.exhibit_docs, state.stats = (
            self.pipeline._collect_exhibit_documents(
                symbol=state.symbol,
                keyword_terms=state.keyword_terms,
                keyword_categories=state.keyword_categories,
                allowed_accessions=state.allowed_accessions,
            )
        )
        if state.exhibit_docs:
            return state

        logger.warning("No exhibit sections found for %s", state.symbol)
        state.done = True
        return state


class DropReferenceStubStage(PipelineStageRunnable[ExhibitRunState]):
    """Drop link-only reference stub chunks."""

    pipeline: ExhibitPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="drop_reference_stubs")

    def _run(self, state: ExhibitRunState) -> ExhibitRunState:
        if state.done:
            return state

        before_stub = len(state.exhibit_docs)
        state.exhibit_docs = [
            doc
            for doc in state.exhibit_docs
            if not self.pipeline._is_reference_stub(doc)
        ]
        if len(state.exhibit_docs) != before_stub:
            logger.info(
                "Dropped %d link-only reference chunks for %s",
                before_stub - len(state.exhibit_docs),
                state.symbol,
            )
        return state


class FilterChunksStage(PipelineStageRunnable[ExhibitRunState]):
    """Apply keyword, dedupe, and per-accession filters."""

    pipeline: ExhibitPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="filter_chunks")

    def _run(self, state: ExhibitRunState) -> ExhibitRunState:
        if state.done:
            return state

        state.filtered_docs = self.pipeline._filter_chunks(
            state.symbol,
            state.exhibit_docs,
        )
        if state.filtered_docs:
            state.stats.log(
                symbol=state.symbol,
                filtered_chunk_count=len(state.filtered_docs),
            )
            log_chunk_length_stats(
                label=None,
                symbol=state.symbol,
                accession=None,
                docs=state.filtered_docs,
                keyword_field="keyword_score",
            )
            return state

        logger.warning(
            "No exhibit chunks remaining after filtering for %s",
            state.symbol,
        )
        state.output_files = write_exhibit_summary(
            symbol=state.symbol,
            docs=state.exhibit_docs,
            config=self.pipeline.config,
        )
        if state.output_files:
            logger.info("Finished processing %s", state.symbol)
        state.done = True
        return state


class ExcludeIndexedAccessionsStage(PipelineStageRunnable[ExhibitRunState]):
    """Skip accessions already present in vector storage."""

    pipeline: ExhibitPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="exclude_indexed_accessions")

    def _run(self, state: ExhibitRunState) -> ExhibitRunState:
        if state.done:
            return state

        if self.pipeline.config.dry_run or self.pipeline._qdrant_client is None:
            return state

        filtered_docs, skipped_count = self.pipeline._filter_indexed_accessions(
            state.filtered_docs
        )
        state.filtered_docs = filtered_docs
        if skipped_count > 0:
            logger.info(
                "Skipped %d chunks from already-indexed accessions for %s",
                skipped_count,
                state.symbol,
            )
        if state.filtered_docs:
            return state

        logger.info("All exhibit chunks already indexed for %s", state.symbol)
        state.done = True
        return state


class IndexAndWriteStage(PipelineStageRunnable[ExhibitRunState]):
    """Index filtered chunks and write symbol-level outputs."""

    pipeline: ExhibitPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="index_and_write")

    def _run(self, state: ExhibitRunState) -> ExhibitRunState:
        if state.done:
            return state

        logger.info(
            "Indexing %d chunks for %s",
            len(state.filtered_docs),
            state.symbol,
        )

        if (
            not self.pipeline.config.dry_run
            and self.pipeline._vector_store is not None
        ):
            vector_docs = prepare_vector_docs(
                state.filtered_docs,
                symbol=state.symbol,
            )
            if vector_docs:
                upload_documents(
                    vector_store=self.pipeline._vector_store,
                    documents=vector_docs,
                    symbol=state.symbol,
                    batch_size=32,
                    desc=f"Uploading vectors for {state.symbol}",
                )
                logger.info(
                    "Stored %d chunks in vector database for %s",
                    len(vector_docs),
                    state.symbol,
                )

        state.output_files = write_exhibit_outputs(
            symbol=state.symbol,
            docs=state.filtered_docs,
            config=self.pipeline.config,
        )
        state.output_files.extend(
            write_exhibit_summary(
                symbol=state.symbol,
                docs=state.exhibit_docs,
                config=self.pipeline.config,
            )
        )
        if state.include_bridge:
            state.bridge_docs = state.filtered_docs
        logger.info("Finished processing %s", state.symbol)
        state.done = True
        return state


def build_exhibit_stage_chain(
    pipeline: ExhibitPipeline,
) -> Runnable[ExhibitRunState, ExhibitRunState]:
    """Build deterministic exhibit stage chain."""
    types_namespace = {"ExhibitPipeline": pipeline.__class__}
    CandidateAccessionsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    CollectExhibitDocsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    DropReferenceStubStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    FilterChunksStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    ExcludeIndexedAccessionsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    IndexAndWriteStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )

    stages: tuple[PipelineStageRunnable[ExhibitRunState], ...] = (
        CandidateAccessionsStage(pipeline=pipeline),
        CollectExhibitDocsStage(pipeline=pipeline),
        DropReferenceStubStage(pipeline=pipeline),
        FilterChunksStage(pipeline=pipeline),
        ExcludeIndexedAccessionsStage(pipeline=pipeline),
        IndexAndWriteStage(pipeline=pipeline),
    )
    configured_stages = tuple(
        stage.configured(pipeline_type=pipeline.pipeline_type)
        for stage in stages
    )
    return pipeline.build_stage_chain(stages=configured_stages)
