# src/sec_nlp/pipelines/presets/financials/run_stages.py
"""Runnable stage helpers for financials pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.runnables import Runnable
from pydantic import Field
from rich.progress import Progress, TaskID

from sec_nlp.pipelines.base.stages import PipelineStageRunnable

from .models import FinancialFact, FinancialStatement
from .steps import (
    DownloadedFiling,
    aggregate_financials,
    build_delta_report,
    download_financial_filings,
    extract_financial_facts,
)
from .steps.aggregate import FinancialDelta

if TYPE_CHECKING:
    from .pipeline import FinancialsPipeline


@dataclass(slots=True)
class FinancialsRunState:
    """In-place state carrier for financials stages from filing download to output write."""

    runtime: FinancialsPipeline
    symbol: str
    progress: Progress | None
    phase_task: TaskID | None
    filings: list[DownloadedFiling] = field(default_factory=list)
    facts: list[FinancialFact] = field(default_factory=list)
    statements: list[FinancialStatement] = field(default_factory=list)
    delta_report: dict[str, FinancialDelta] = field(default_factory=dict)
    outputs: list[Path] = field(default_factory=list)
    metadata: dict[str, int | str] = field(default_factory=dict)


def create_initial_financials_state(
    *,
    runtime: FinancialsPipeline,
    symbol: str,
    progress: Progress | None,
    phase_task: TaskID | None,
) -> FinancialsRunState:
    """Create initial mutable state for financials runnable stages."""
    return FinancialsRunState(
        runtime=runtime,
        symbol=symbol,
        progress=progress,
        phase_task=phase_task,
    )


class DownloadFilingsStage(PipelineStageRunnable[FinancialsRunState]):
    """Ingress acquisition stage that downloads filing accession directories by symbol."""

    name: str = Field(default="download_filings")

    def _run(self, state: FinancialsRunState) -> FinancialsRunState:
        """Execute the download filings stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Downloading",
        )
        state.filings = download_financial_filings(
            symbol=state.symbol,
            settings=state.runtime.config,
        )
        return state


class ExtractFactsStage(PipelineStageRunnable[FinancialsRunState]):
    """Extraction stage that converts downloaded filings into normalized fact rows."""

    name: str = Field(default="extract_facts")

    def _run(self, state: FinancialsRunState) -> FinancialsRunState:
        """Execute the extract facts stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Extracting",
            total=len(state.filings),
        )
        parser = state.runtime._get_parser()
        state.facts = []
        for filing in state.filings:
            state.facts.extend(
                extract_financial_facts(
                    symbol=state.symbol,
                    filing=filing,
                    parser=parser,
                )
            )
            if state.progress is not None and state.phase_task is not None:
                state.progress.advance(state.phase_task)
        return state


class AggregateFinancialsStage(PipelineStageRunnable[FinancialsRunState]):
    """Aggregation stage that composes extracted facts into statement-level rows."""

    name: str = Field(default="aggregate_financials")

    def _run(self, state: FinancialsRunState) -> FinancialsRunState:
        """Execute the aggregate financials stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Aggregating",
        )
        state.statements = aggregate_financials(
            state.facts,
            compute_ratios=state.runtime.config.compute_ratios,
        )
        return state


class BuildDeltaReportStage(PipelineStageRunnable[FinancialsRunState]):
    """Delta stage that computes period-over-period statement changes when enabled."""

    name: str = Field(default="build_delta_report")

    def _run(self, state: FinancialsRunState) -> FinancialsRunState:
        """Execute the build delta report stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Delta report",
        )
        state.delta_report = (
            build_delta_report(state.statements)
            if state.runtime.config.include_delta_report
            else {}
        )
        return state


class WriteFinancialsOutputsStage(PipelineStageRunnable[FinancialsRunState]):
    """Egress stage that writes financial artifacts and summary metadata."""

    name: str = Field(default="write_outputs")

    def _run(self, state: FinancialsRunState) -> FinancialsRunState:
        """Execute the write financials outputs stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Writing",
        )
        state.outputs = state.runtime._write_outputs(
            symbol=state.symbol,
            filings_processed=len(state.filings),
            statements=state.statements,
            delta_report=state.delta_report,
        )
        state.metadata = {
            "filings_processed": len(state.filings),
            "facts_extracted": len(state.facts),
            "periods_generated": len(state.statements),
        }
        return state


def build_financials_stage_chain(
    pipeline: FinancialsPipeline,
) -> Runnable[FinancialsRunState, FinancialsRunState]:
    """Build deterministic financials stage chain."""
    stages: tuple[PipelineStageRunnable[FinancialsRunState], ...] = (
        DownloadFilingsStage(),
        ExtractFactsStage(),
        AggregateFinancialsStage(),
        BuildDeltaReportStage(),
        WriteFinancialsOutputsStage(),
    )
    return pipeline.build_stage_chain(
        stages=pipeline.configure_stage_runnables(stages=stages)
    )
