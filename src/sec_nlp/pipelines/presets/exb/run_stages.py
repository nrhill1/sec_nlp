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
from sec_nlp.pipelines.observability.telemetry import log_chunk_length_stats
from sec_nlp.pipelines.runtime import prepare_vector_docs
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
    """In-place state carrier for exhibit stages from accession scoping to output write."""

    runtime: ExhibitPipeline
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


class CandidateAccessionsStage(PipelineStageRunnable[ExhibitRunState]):
    """Scope stage that narrows accession search space before expensive exhibit extraction."""

    name: str = Field(default="candidate_accessions")

    def _run(self, state: ExhibitRunState) -> ExhibitRunState:
        """Execute the candidate accessions stage and return updated run state."""
        log_divider(logger, color="cyan")
        logger.info("Processing symbol: %s \n", state.symbol)

        if not (
            state.runtime.config.candidate_first
            and state.runtime.config.has_contract_exhibits()
        ):
            return state

        state.allowed_accessions = state.runtime._build_candidate_accessions(
            state.symbol
        )
        if state.allowed_accessions:
            logger.info(
                "Candidate-first narrowed %s to %d accessions",
                state.symbol,
                len(state.allowed_accessions),
            )
            return state

        if state.runtime.config.candidate_fallback_full_scan:
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
    """Acquisition stage that extracts exhibit documents and keyword classification data."""

    name: str = Field(default="collect_exhibit_docs")

    def _run(self, state: ExhibitRunState) -> ExhibitRunState:
        """Execute the collect exhibit docs stage and return updated run state."""
        if state.done:
            return state

        state.runtime._loader.add_symbol(state.symbol)
        if state.runtime.config.has_contract_exhibits():
            state.keyword_terms = [
                term.lower()
                for term in state.runtime.config.search_terms
                if term
            ]
        state.keyword_categories = KeywordMatcher.build_keyword_categories(
            state.keyword_terms,
            category_terms=CONTRACT_KEYWORD_CATEGORY_TERMS,
        )

        state.exhibit_docs, state.stats = (
            state.runtime._collect_exhibit_documents(
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
    """Cleanup stage that removes non-substantive reference-only exhibit chunks."""

    name: str = Field(default="drop_reference_stubs")

    def _run(self, state: ExhibitRunState) -> ExhibitRunState:
        """Execute the drop reference stub stage and return updated run state."""
        if state.done:
            return state

        before_stub = len(state.exhibit_docs)
        state.exhibit_docs = [
            doc
            for doc in state.exhibit_docs
            if not state.runtime._is_reference_stub(doc)
        ]
        if len(state.exhibit_docs) != before_stub:
            logger.info(
                "Dropped %d link-only reference chunks for %s",
                before_stub - len(state.exhibit_docs),
                state.symbol,
            )
        return state


class FilterChunksStage(PipelineStageRunnable[ExhibitRunState]):
    """Selection stage that enforces keyword, dedupe, and per-accession chunk policies."""

    name: str = Field(default="filter_chunks")

    def _run(self, state: ExhibitRunState) -> ExhibitRunState:
        """Execute the filter chunks stage and return updated run state."""
        if state.done:
            return state

        state.filtered_docs = state.runtime._filter_chunks(
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
            config=state.runtime.config,
        )
        if state.output_files:
            logger.info("Finished processing %s", state.symbol)
        state.done = True
        return state


class ExcludeIndexedAccessionsStage(PipelineStageRunnable[ExhibitRunState]):
    """Deduplication stage that excludes accessions already indexed in vector storage."""

    name: str = Field(default="exclude_indexed_accessions")

    def _run(self, state: ExhibitRunState) -> ExhibitRunState:
        """Execute the exclude indexed accessions stage and return updated run state."""
        if state.done:
            return state

        if state.runtime.config.dry_run or state.runtime._qdrant_client is None:
            return state

        filtered_docs, skipped_count = state.runtime._filter_indexed_accessions(
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
    """Egress stage that indexes surviving chunks and writes symbol-level artifacts."""

    name: str = Field(default="index_and_write")

    def _run(self, state: ExhibitRunState) -> ExhibitRunState:
        """Execute the index and write stage and return updated run state."""
        if state.done:
            return state

        logger.info(
            "Indexing %d chunks for %s",
            len(state.filtered_docs),
            state.symbol,
        )

        if (
            not state.runtime.config.dry_run
            and state.runtime._vector_store is not None
        ):
            vector_docs = prepare_vector_docs(
                state.filtered_docs,
                symbol=state.symbol,
            )
            if vector_docs:
                upload_documents(
                    vector_store=state.runtime._vector_store,
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
            config=state.runtime.config,
        )
        state.output_files.extend(
            write_exhibit_summary(
                symbol=state.symbol,
                docs=state.exhibit_docs,
                config=state.runtime.config,
            )
        )
        if state.include_bridge:
            state.bridge_docs = state.filtered_docs
        logger.info("Finished processing %s", state.symbol)
        state.done = True
        return state


_EXHIBIT_STAGES: tuple[PipelineStageRunnable[ExhibitRunState], ...] = (
    CandidateAccessionsStage(),
    CollectExhibitDocsStage(),
    DropReferenceStubStage(),
    FilterChunksStage(),
    ExcludeIndexedAccessionsStage(),
    IndexAndWriteStage(),
)


def build_exhibit_stage_chain(
    pipeline: ExhibitPipeline,
) -> Runnable[ExhibitRunState, ExhibitRunState]:
    """Build deterministic exhibit stage chain."""
    return pipeline.build_configured_stage_chain(stages=_EXHIBIT_STAGES)
