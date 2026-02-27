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
    """Mutable in-process state shared across insider runnable stages."""

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
    symbol: str,
    progress: Progress | None,
    phase_task: TaskID | None,
) -> InsiderRunState:
    """Create initial mutable state for insider runnable stage execution."""
    return InsiderRunState(
        symbol=symbol,
        progress=progress,
        phase_task=phase_task,
    )


class DownloadInsiderFilingsStage(PipelineStageRunnable[InsiderRunState]):
    """Download insider filings for one symbol."""

    pipeline: InsiderPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="download_filings")

    def _run(self, state: InsiderRunState) -> InsiderRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Downloading",
        )
        state.filings = download_insider_filings(
            symbol=state.symbol,
            settings=self.pipeline.config,
        )
        return state


class ParseInsiderTransactionsStage(PipelineStageRunnable[InsiderRunState]):
    """Parse insider transaction rows from downloaded filings."""

    pipeline: InsiderPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="parse_transactions")

    def _run(self, state: InsiderRunState) -> InsiderRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Parsing",
            total=len(state.filings),
        )
        parser = self.pipeline._get_parser()
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
    """Aggregate insider transactions into ledgers and clusters."""

    pipeline: InsiderPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="aggregate_activity")

    def _run(self, state: InsiderRunState) -> InsiderRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Aggregating",
        )
        state.ledgers = build_insider_ledgers(state.transactions)
        state.clusters = find_trade_clusters(
            state.transactions,
            window_days=self.pipeline.config.alert_window_days,
            cluster_threshold=self.pipeline.config.alert_cluster_threshold,
        )
        state.net_buy_ratio = compute_net_buy_ratio(state.transactions)
        return state


class CorrelateInsiderActivityStage(PipelineStageRunnable[InsiderRunState]):
    """Correlate insider activity with market and filing signals."""

    pipeline: InsiderPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="correlate_activity")

    def _run(self, state: InsiderRunState) -> InsiderRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Correlating",
        )
        state.alerts, state.correlation_meta = correlate_insider_activity(
            symbol=state.symbol,
            transactions=state.transactions,
            clusters=state.clusters,
            settings=self.pipeline.config,
        )
        return state


class WriteInsiderOutputsStage(PipelineStageRunnable[InsiderRunState]):
    """Write insider output artifacts and summary metadata."""

    pipeline: InsiderPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="write_outputs")

    def _run(self, state: InsiderRunState) -> InsiderRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Writing",
        )
        state.outputs = self.pipeline._write_outputs(
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


def build_insider_stage_chain(
    pipeline: InsiderPipeline,
) -> Runnable[InsiderRunState, InsiderRunState]:
    """Build deterministic insider stage chain."""
    types_namespace = {"InsiderPipeline": pipeline.__class__}
    DownloadInsiderFilingsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    ParseInsiderTransactionsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    AggregateInsiderActivityStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    CorrelateInsiderActivityStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    WriteInsiderOutputsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    stages: tuple[PipelineStageRunnable[InsiderRunState], ...] = (
        DownloadInsiderFilingsStage(pipeline=pipeline),
        ParseInsiderTransactionsStage(pipeline=pipeline),
        AggregateInsiderActivityStage(pipeline=pipeline),
        CorrelateInsiderActivityStage(pipeline=pipeline),
        WriteInsiderOutputsStage(pipeline=pipeline),
    )
    configured_stages = tuple(
        stage.configured(
            pipeline_type=pipeline.pipeline_type,
            run_id=str(pipeline.config.run_id),
        )
        for stage in stages
    )
    return pipeline.build_stage_chain(stages=configured_stages)
