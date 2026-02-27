# src/sec_nlp/pipelines/presets/news/run_stages.py
"""Runnable stage helpers for news pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.runnables import RunnableLambda
from rich.progress import Progress, TaskID

from .models import NewsCorrelation, NewsHeadline, NewsTimelineEntry
from .steps import (
    correlate_news_items,
    fetch_news_items,
    match_news_items,
    resolve_symbol_aliases,
)

if TYPE_CHECKING:
    from .pipeline import NewsPipeline


@dataclass(slots=True)
class NewsRunState:
    """Mutable in-process state shared across news runnable stages."""

    symbol: str
    progress: Progress | None
    phase_task: TaskID | None
    symbol_aliases: list[str] = field(default_factory=list)
    fetched_items: list[NewsHeadline] = field(default_factory=list)
    matched_items: list[NewsHeadline] = field(default_factory=list)
    correlated_items: list[NewsHeadline] = field(default_factory=list)
    timeline: list[NewsTimelineEntry] = field(default_factory=list)
    correlation: NewsCorrelation = field(default_factory=NewsCorrelation)
    outputs: list[Path] = field(default_factory=list)
    metadata: dict[str, int | float | str | None] = field(default_factory=dict)


def create_initial_news_state(
    *,
    symbol: str,
    progress: Progress | None,
    phase_task: TaskID | None,
) -> NewsRunState:
    """Create initial mutable state for news runnable stage execution."""
    return NewsRunState(
        symbol=symbol,
        progress=progress,
        phase_task=phase_task,
    )


@dataclass(slots=True)
class NewsStageRunner:
    """Bound stage methods to avoid per-stage lambda/closure allocations."""

    pipeline: NewsPipeline

    def resolve_aliases(self, state: NewsRunState) -> NewsRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Resolving aliases",
        )
        state.symbol_aliases = resolve_symbol_aliases(
            symbol=state.symbol,
            settings=self.pipeline.config,
        )
        return state

    def fetch(self, state: NewsRunState) -> NewsRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Fetching",
        )
        state.fetched_items = fetch_news_items(
            symbol=state.symbol,
            settings=self.pipeline.config,
        )
        return state

    def match(self, state: NewsRunState) -> NewsRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Matching",
        )
        state.matched_items = match_news_items(
            items=state.fetched_items,
            symbol=state.symbol,
            topics=self.pipeline.config.topics,
            min_relevance=self.pipeline.config.min_relevance,
            require_symbol_match=self.pipeline.config.require_symbol_match,
            symbol_aliases=state.symbol_aliases,
        )
        return state

    def correlate(self, state: NewsRunState) -> NewsRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Correlating",
        )
        state.correlated_items, state.timeline, state.correlation = (
            correlate_news_items(
                symbol=state.symbol,
                items=state.matched_items,
                settings=self.pipeline.config,
            )
        )
        return state

    def write(self, state: NewsRunState) -> NewsRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Writing",
        )
        state.outputs = self.pipeline._write_outputs(
            symbol=state.symbol,
            items=state.correlated_items,
            timeline=state.timeline,
            correlation=state.correlation,
            symbol_aliases=state.symbol_aliases,
        )
        state.metadata = {
            "items_fetched": len(state.fetched_items),
            "items_emitted": len(state.correlated_items),
            "timeline_days": len(state.timeline),
            "days_compared": state.correlation.days_compared,
            "news_to_return_correlation": state.correlation.news_to_return_correlation,
            "filings_linked": state.correlation.filings_linked,
            "clusters_detected": len(state.correlation.clusters),
            "symbol_alias_count": len(state.symbol_aliases),
        }
        return state


def build_news_stage_runnables(
    pipeline: NewsPipeline,
) -> tuple[RunnableLambda[NewsRunState, NewsRunState], ...]:
    """Build deterministic news stage runnables."""
    runner = NewsStageRunner(pipeline)
    return pipeline.build_stage_runnables(
        named_stages=(
            ("resolve_aliases", runner.resolve_aliases),
            ("fetch_items", runner.fetch),
            ("match_items", runner.match),
            ("correlate_items", runner.correlate),
            ("write_outputs", runner.write),
        )
    )
