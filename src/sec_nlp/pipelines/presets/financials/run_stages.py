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
    """Mutable in-process state shared across financials runnable stages."""

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
    symbol: str,
    progress: Progress | None,
    phase_task: TaskID | None,
) -> FinancialsRunState:
    """Create initial mutable state for financials runnable stages."""
    return FinancialsRunState(
        symbol=symbol,
        progress=progress,
        phase_task=phase_task,
    )


class DownloadFilingsStage(PipelineStageRunnable[FinancialsRunState]):
    """Download filing accession directories for one symbol."""

    pipeline: FinancialsPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="download_filings")

    def _run(self, state: FinancialsRunState) -> FinancialsRunState:
        """Execute the download filings stage and return updated run state."""
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Downloading",
        )
        state.filings = download_financial_filings(
            symbol=state.symbol,
            settings=self.pipeline.config,
        )
        return state


class ExtractFactsStage(PipelineStageRunnable[FinancialsRunState]):
    """Extract normalized financial facts from downloaded filings."""

    pipeline: FinancialsPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="extract_facts")

    def _run(self, state: FinancialsRunState) -> FinancialsRunState:
        """Execute the extract facts stage and return updated run state."""
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Extracting",
            total=len(state.filings),
        )
        parser = self.pipeline._get_parser()
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
    """Aggregate extracted facts into statement rows."""

    pipeline: FinancialsPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="aggregate_financials")

    def _run(self, state: FinancialsRunState) -> FinancialsRunState:
        """Execute the aggregate financials stage and return updated run state."""
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Aggregating",
        )
        state.statements = aggregate_financials(
            state.facts,
            compute_ratios=self.pipeline.config.compute_ratios,
        )
        return state


class BuildDeltaReportStage(PipelineStageRunnable[FinancialsRunState]):
    """Compute period-over-period deltas when enabled."""

    pipeline: FinancialsPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="build_delta_report")

    def _run(self, state: FinancialsRunState) -> FinancialsRunState:
        """Execute the build delta report stage and return updated run state."""
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Delta report",
        )
        state.delta_report = (
            build_delta_report(state.statements)
            if self.pipeline.config.include_delta_report
            else {}
        )
        return state


class WriteFinancialsOutputsStage(PipelineStageRunnable[FinancialsRunState]):
    """Write financial output artifacts and summary metadata."""

    pipeline: FinancialsPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="write_outputs")

    def _run(self, state: FinancialsRunState) -> FinancialsRunState:
        """Execute the write financials outputs stage and return updated run state."""
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Writing",
        )
        state.outputs = self.pipeline._write_outputs(
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
    types_namespace = {"FinancialsPipeline": pipeline.__class__}
    DownloadFilingsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    ExtractFactsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    AggregateFinancialsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    BuildDeltaReportStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    WriteFinancialsOutputsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    stages: tuple[PipelineStageRunnable[FinancialsRunState], ...] = (
        DownloadFilingsStage(pipeline=pipeline),
        ExtractFactsStage(pipeline=pipeline),
        AggregateFinancialsStage(pipeline=pipeline),
        BuildDeltaReportStage(pipeline=pipeline),
        WriteFinancialsOutputsStage(pipeline=pipeline),
    )
    configured_stages = tuple(
        stage.configured(
            pipeline_type=pipeline.pipeline_type,
            run_id=str(pipeline.config.run_id),
        )
        for stage in stages
    )
    return pipeline.build_stage_chain(stages=configured_stages)
