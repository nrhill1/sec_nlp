# src/sec_nlp/pipelines/presets/insider/run_stages.py
"""Runnable stage helpers for insider pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.runnables import Runnable
from pydantic import Field
from rich.progress import Progress, TaskID

from sec_nlp.pipelines.base.stages import PipelineStageRunnable

from .models import InsiderAlert, InsiderLedger, InsiderTransaction
from .steps import (
    DownloadedInsiderFiling,
    TradeCluster,
    build_insider_ledgers,
    compute_net_buy_ratio,
    correlate_insider_activity,
    download_insider_filings,
    find_trade_clusters,
    parse_insider_transactions,
)

if TYPE_CHECKING:
    from .pipeline import InsiderPipeline


@dataclass(slots=True)
class InsiderRunState:
    """In-place state carrier for insider stages from filing download to output write."""

    runtime: InsiderPipeline
    symbol: str
    progress: Progress | None
    phase_task: TaskID | None
    filings: list[DownloadedInsiderFiling] = field(default_factory=list)
    transactions: list[InsiderTransaction] = field(default_factory=list)
    ledgers: list[InsiderLedger] = field(default_factory=list)
    alerts: list[InsiderAlert] = field(default_factory=list)
    clusters: list[TradeCluster] = field(default_factory=list)
    net_buy_ratio: float | None = None
    correlation_meta: dict[str, int] = field(default_factory=dict)
    outputs: list[Path] = field(default_factory=list)
    metadata: dict[str, int | float | str | None] = field(default_factory=dict)


def create_initial_insider_state(
    *,
    runtime: InsiderPipeline,
    symbol: str,
    progress: Progress | None,
    phase_task: TaskID | None,
) -> InsiderRunState:
    """Create initial mutable state for insider runnable stage execution."""
    return InsiderRunState(
        runtime=runtime,
        symbol=symbol,
        progress=progress,
        phase_task=phase_task,
    )


class DownloadInsiderFilingsStage(PipelineStageRunnable[InsiderRunState]):
    """Ingress acquisition stage that downloads insider filings for a symbol."""

    name: str = Field(default="download_filings")

    def _run(self, state: InsiderRunState) -> InsiderRunState:
        """Execute the download insider filings stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Downloading",
        )
        state.filings = download_insider_filings(
            symbol=state.symbol,
            settings=state.runtime.config,
        )
        return state


class ParseInsiderTransactionsStage(PipelineStageRunnable[InsiderRunState]):
    """Parsing stage that extracts transaction rows from downloaded insider filings."""

    name: str = Field(default="parse_transactions")

    def _run(self, state: InsiderRunState) -> InsiderRunState:
        """Execute the parse insider transactions stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Parsing",
            total=len(state.filings),
        )
        parser = state.runtime._get_parser()
        state.transactions = []
        for filing in state.filings:
            state.transactions.extend(
                parse_insider_transactions(
                    symbol=state.symbol,
                    filing=filing,
                    parser=parser,
                )
            )
            if state.progress is not None and state.phase_task is not None:
                state.progress.advance(state.phase_task)
        return state


class AggregateInsiderActivityStage(PipelineStageRunnable[InsiderRunState]):
    """Aggregation stage that derives ledgers, clusters, and buy ratio signals."""

    name: str = Field(default="aggregate_activity")

    def _run(self, state: InsiderRunState) -> InsiderRunState:
        """Execute the aggregate insider activity stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Aggregating",
        )
        state.ledgers = build_insider_ledgers(state.transactions)
        state.clusters = find_trade_clusters(
            state.transactions,
            window_days=state.runtime.config.alert_window_days,
            cluster_threshold=state.runtime.config.alert_cluster_threshold,
        )
        state.net_buy_ratio = compute_net_buy_ratio(state.transactions)
        return state


class CorrelateInsiderActivityStage(PipelineStageRunnable[InsiderRunState]):
    """Correlation stage that maps insider activity to market and filing context."""

    name: str = Field(default="correlate_activity")

    def _run(self, state: InsiderRunState) -> InsiderRunState:
        """Execute the correlate insider activity stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Correlating",
        )
        state.alerts, state.correlation_meta = correlate_insider_activity(
            symbol=state.symbol,
            transactions=state.transactions,
            clusters=state.clusters,
            settings=state.runtime.config,
        )
        return state


class WriteInsiderOutputsStage(PipelineStageRunnable[InsiderRunState]):
    """Egress stage that writes insider artifacts and summary metadata."""

    name: str = Field(default="write_outputs")

    def _run(self, state: InsiderRunState) -> InsiderRunState:
        """Execute the write insider outputs stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Writing",
        )
        state.outputs = state.runtime._write_outputs(
            symbol=state.symbol,
            filings_processed=len(state.filings),
            transactions=state.transactions,
            ledgers=state.ledgers,
            alerts=state.alerts,
            net_buy_ratio=state.net_buy_ratio,
            clusters=state.clusters,
            correlation_meta=state.correlation_meta,
        )
        state.metadata = {
            "filings_processed": len(state.filings),
            "transactions_processed": len(state.transactions),
            "ledger_rows": len(state.ledgers),
            "clusters_detected": len(state.clusters),
            "alerts_generated": len(state.alerts),
            "net_buy_ratio": state.net_buy_ratio,
            "material_filings_considered": int(
                state.correlation_meta.get("material_filings_considered", 0)
            ),
            "market_windows_evaluated": int(
                state.correlation_meta.get("market_windows_evaluated", 0)
            ),
        }
        return state


_INSIDER_STAGES: tuple[PipelineStageRunnable[InsiderRunState], ...] = (
    DownloadInsiderFilingsStage(),
    ParseInsiderTransactionsStage(),
    AggregateInsiderActivityStage(),
    CorrelateInsiderActivityStage(),
    WriteInsiderOutputsStage(),
)


def build_insider_stage_chain(
    pipeline: InsiderPipeline,
) -> Runnable[InsiderRunState, InsiderRunState]:
    """Build deterministic insider stage chain."""
    return pipeline.build_stage_chain(
        stages=pipeline.configure_stage_runnables(stages=_INSIDER_STAGES)
    )
