# src/sec_nlp/pipelines/presets/holdings/run_stages.py
"""Runnable stage helpers for holdings pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.runnables import Runnable
from pydantic import Field
from rich.progress import Progress, TaskID

from sec_nlp.pipelines.base.stages import PipelineStageRunnable

from .models import HoldingPosition, HoldingsDiff, OwnershipSummary
from .steps import (
    DownloadedHoldingsFiling,
    build_holdings_diffs,
    build_ownership_summary,
    download_holdings_filings,
    parse_holding_positions,
)

if TYPE_CHECKING:
    from .pipeline import HoldingsPipeline


@dataclass(slots=True)
class HoldingsRunState:
    """Mutable in-process state shared across holdings runnable stages."""

    symbol: str
    progress: Progress | None
    phase_task: TaskID | None
    filings: list[DownloadedHoldingsFiling] = field(default_factory=list)
    positions: list[HoldingPosition] = field(default_factory=list)
    diffs: list[HoldingsDiff] = field(default_factory=list)
    summary: OwnershipSummary | None = None
    outputs: list[Path] = field(default_factory=list)
    metadata: dict[str, int | float | str | None] = field(default_factory=dict)


def create_initial_holdings_state(
    *,
    symbol: str,
    progress: Progress | None,
    phase_task: TaskID | None,
) -> HoldingsRunState:
    """Create initial mutable state for holdings runnable stage execution."""
    return HoldingsRunState(
        symbol=symbol,
        progress=progress,
        phase_task=phase_task,
    )


class DownloadHoldingsFilingsStage(PipelineStageRunnable[HoldingsRunState]):
    """Download holdings filings for one symbol."""

    pipeline: HoldingsPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="download_filings")

    def _run(self, state: HoldingsRunState) -> HoldingsRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Downloading",
        )
        state.filings = download_holdings_filings(
            symbol=state.symbol,
            settings=self.pipeline.config,
        )
        return state


class ParseHoldingsPositionsStage(PipelineStageRunnable[HoldingsRunState]):
    """Parse holdings positions from downloaded filing content."""

    pipeline: HoldingsPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="parse_positions")

    def _run(self, state: HoldingsRunState) -> HoldingsRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Parsing",
            total=len(state.filings),
        )
        parser = self.pipeline._get_parser()
        state.positions = []
        for filing in state.filings:
            state.positions.extend(
                parse_holding_positions(
                    symbol=state.symbol,
                    filing=filing,
                    parser=parser,
                    cusip_filter=self.pipeline.config.cusip,
                )
            )
            if state.progress is not None and state.phase_task is not None:
                state.progress.advance(state.phase_task)
        return state


class DiffHoldingsPositionsStage(PipelineStageRunnable[HoldingsRunState]):
    """Compute quarter-over-quarter holding diffs."""

    pipeline: HoldingsPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="diff_positions")

    def _run(self, state: HoldingsRunState) -> HoldingsRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Diffing",
        )
        state.diffs = build_holdings_diffs(
            symbol=state.symbol,
            positions=state.positions,
        )
        return state


class AggregateHoldingsSummaryStage(PipelineStageRunnable[HoldingsRunState]):
    """Build holdings ownership summary from parsed positions."""

    pipeline: HoldingsPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="aggregate_summary")

    def _run(self, state: HoldingsRunState) -> HoldingsRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Aggregating",
        )
        state.summary = build_ownership_summary(
            symbol=state.symbol,
            positions=state.positions,
            top_holders=self.pipeline.config.top_holders,
            cusip_filter=self.pipeline.config.cusip,
        )
        return state


class WriteHoldingsOutputsStage(PipelineStageRunnable[HoldingsRunState]):
    """Write holdings output artifacts and summary metadata."""

    pipeline: HoldingsPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="write_outputs")

    def _run(self, state: HoldingsRunState) -> HoldingsRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Writing",
        )
        summary = state.summary
        if summary is None:
            summary = build_ownership_summary(
                symbol=state.symbol,
                positions=state.positions,
                top_holders=self.pipeline.config.top_holders,
                cusip_filter=self.pipeline.config.cusip,
            )
            state.summary = summary
        state.outputs = self.pipeline._write_outputs(
            symbol=state.symbol,
            filings_processed=len(state.filings),
            positions=state.positions,
            diffs=state.diffs,
            summary=summary,
        )
        state.metadata = {
            "filings_processed": len(state.filings),
            "positions_processed": len(state.positions),
            "diffs_generated": len(state.diffs),
            "latest_accession": summary.latest_accession,
            "total_value_thousands": summary.total_value_thousands,
            "concentration_hhi": summary.concentration_hhi,
            "filtered_positions": summary.filtered_positions,
        }
        return state


def build_holdings_stage_chain(
    pipeline: HoldingsPipeline,
) -> Runnable[HoldingsRunState, HoldingsRunState]:
    """Build deterministic holdings stage chain."""
    types_namespace = {"HoldingsPipeline": pipeline.__class__}
    DownloadHoldingsFilingsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    ParseHoldingsPositionsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    DiffHoldingsPositionsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    AggregateHoldingsSummaryStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    WriteHoldingsOutputsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    stages: tuple[PipelineStageRunnable[HoldingsRunState], ...] = (
        DownloadHoldingsFilingsStage(pipeline=pipeline),
        ParseHoldingsPositionsStage(pipeline=pipeline),
        DiffHoldingsPositionsStage(pipeline=pipeline),
        AggregateHoldingsSummaryStage(pipeline=pipeline),
        WriteHoldingsOutputsStage(pipeline=pipeline),
    )
    configured_stages = tuple(
        stage.configured(
            pipeline_type=pipeline.pipeline_type,
            run_id=str(pipeline.config.run_id),
        )
        for stage in stages
    )
    return pipeline.build_stage_chain(stages=configured_stages)
