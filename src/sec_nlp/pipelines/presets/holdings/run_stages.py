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
    """In-place state carrier for holdings stages from filing download to output write."""

    runtime: HoldingsPipeline
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
    runtime: HoldingsPipeline,
    symbol: str,
    progress: Progress | None,
    phase_task: TaskID | None,
) -> HoldingsRunState:
    """Create initial mutable state for holdings runnable stage execution."""
    return HoldingsRunState(
        runtime=runtime,
        symbol=symbol,
        progress=progress,
        phase_task=phase_task,
    )


class DownloadHoldingsFilingsStage(PipelineStageRunnable[HoldingsRunState]):
    """Ingress acquisition stage that downloads holdings filings for a symbol."""

    name: str = Field(default="download_filings")

    def _run(self, state: HoldingsRunState) -> HoldingsRunState:
        """Execute the download holdings filings stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Downloading",
        )
        state.filings = download_holdings_filings(
            symbol=state.symbol,
            settings=state.runtime.config,
        )
        return state


class ParseHoldingsPositionsStage(PipelineStageRunnable[HoldingsRunState]):
    """Parsing stage that extracts position rows from downloaded holdings filings."""

    name: str = Field(default="parse_positions")

    def _run(self, state: HoldingsRunState) -> HoldingsRunState:
        """Execute the parse holdings positions stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Parsing",
            total=len(state.filings),
        )
        parser = state.runtime._get_parser()
        state.positions = []
        for filing in state.filings:
            state.positions.extend(
                parse_holding_positions(
                    symbol=state.symbol,
                    filing=filing,
                    parser=parser,
                    cusip_filter=state.runtime.config.cusip,
                )
            )
            if state.progress is not None and state.phase_task is not None:
                state.progress.advance(state.phase_task)
        return state


class DiffHoldingsPositionsStage(PipelineStageRunnable[HoldingsRunState]):
    """Diff stage that computes quarter-over-quarter ownership position changes."""

    name: str = Field(default="diff_positions")

    def _run(self, state: HoldingsRunState) -> HoldingsRunState:
        """Execute the diff holdings positions stage and return updated run state."""
        state.runtime._update_phase(
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
    """Aggregation stage that builds ownership summary metrics from parsed positions."""

    name: str = Field(default="aggregate_summary")

    def _run(self, state: HoldingsRunState) -> HoldingsRunState:
        """Execute the aggregate holdings summary stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Aggregating",
        )
        state.summary = build_ownership_summary(
            symbol=state.symbol,
            positions=state.positions,
            top_holders=state.runtime.config.top_holders,
            cusip_filter=state.runtime.config.cusip,
        )
        return state


class WriteHoldingsOutputsStage(PipelineStageRunnable[HoldingsRunState]):
    """Egress stage that writes holdings artifacts and summary metadata."""

    name: str = Field(default="write_outputs")

    def _run(self, state: HoldingsRunState) -> HoldingsRunState:
        """Execute the write holdings outputs stage and return updated run state."""
        state.runtime._update_phase(
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
                top_holders=state.runtime.config.top_holders,
                cusip_filter=state.runtime.config.cusip,
            )
            state.summary = summary
        state.outputs = state.runtime._write_outputs(
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


_HOLDINGS_STAGES: tuple[PipelineStageRunnable[HoldingsRunState], ...] = (
    DownloadHoldingsFilingsStage(),
    ParseHoldingsPositionsStage(),
    DiffHoldingsPositionsStage(),
    AggregateHoldingsSummaryStage(),
    WriteHoldingsOutputsStage(),
)


def build_holdings_stage_chain(
    pipeline: HoldingsPipeline,
) -> Runnable[HoldingsRunState, HoldingsRunState]:
    """Build deterministic holdings stage chain."""
    return pipeline.build_stage_chain(
        stages=pipeline.configure_stage_runnables(stages=_HOLDINGS_STAGES)
    )
