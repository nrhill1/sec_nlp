# src/sec_nlp/pipelines/presets/financials/run_stages.py
"""Runnable stage helpers for financials pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.runnables import RunnableLambda
from rich.progress import Progress, TaskID

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


@dataclass(slots=True)
class FinancialsStageRunner:
    """Bound stage methods to avoid per-stage lambda/closure allocations."""

    pipeline: FinancialsPipeline

    def download(self, state: FinancialsRunState) -> FinancialsRunState:
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

    def extract(self, state: FinancialsRunState) -> FinancialsRunState:
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

    def aggregate(self, state: FinancialsRunState) -> FinancialsRunState:
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

    def build_delta(self, state: FinancialsRunState) -> FinancialsRunState:
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

    def write(self, state: FinancialsRunState) -> FinancialsRunState:
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


def build_financials_stage_runnables(
    pipeline: FinancialsPipeline,
) -> tuple[RunnableLambda[FinancialsRunState, FinancialsRunState], ...]:
    """Build deterministic financials stage runnables."""
    runner = FinancialsStageRunner(pipeline)
    return pipeline.build_stage_runnables(
        named_stages=(
            ("download_filings", runner.download),
            ("extract_facts", runner.extract),
            ("aggregate_financials", runner.aggregate),
            ("build_delta_report", runner.build_delta),
            ("write_outputs", runner.write),
        )
    )
