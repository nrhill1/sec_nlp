# src/sec_nlp/pipelines/presets/news/run_stages.py
"""Runnable stage helpers for news pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.runnables import Runnable
from pydantic import Field
from rich.progress import Progress, TaskID

from sec_nlp.pipelines.base.stages import PipelineStageRunnable

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


class ResolveAliasesStage(PipelineStageRunnable[NewsRunState]):
    """Resolve symbol aliases used by matching logic."""

    pipeline: NewsPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="resolve_aliases")

    def _run(self, state: NewsRunState) -> NewsRunState:
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


class FetchItemsStage(PipelineStageRunnable[NewsRunState]):
    """Fetch raw news items for one symbol."""

    pipeline: NewsPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="fetch_items")

    def _run(self, state: NewsRunState) -> NewsRunState:
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


class MatchItemsStage(PipelineStageRunnable[NewsRunState]):
    """Filter and match fetched items against configured topics."""

    pipeline: NewsPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="match_items")

    def _run(self, state: NewsRunState) -> NewsRunState:
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


class CorrelateItemsStage(PipelineStageRunnable[NewsRunState]):
    """Correlate matched headlines with timeline and market data."""

    pipeline: NewsPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="correlate_items")

    def _run(self, state: NewsRunState) -> NewsRunState:
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


class WriteOutputsStage(PipelineStageRunnable[NewsRunState]):
    """Write symbol-level outputs and metadata."""

    pipeline: NewsPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="write_outputs")

    def _run(self, state: NewsRunState) -> NewsRunState:
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


def build_news_stage_chain(
    pipeline: NewsPipeline,
) -> Runnable[NewsRunState, NewsRunState]:
    """Build deterministic news stage chain."""
    types_namespace = {"NewsPipeline": pipeline.__class__}
    ResolveAliasesStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    FetchItemsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    MatchItemsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    CorrelateItemsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    WriteOutputsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    stages: tuple[PipelineStageRunnable[NewsRunState], ...] = (
        ResolveAliasesStage(pipeline=pipeline),
        FetchItemsStage(pipeline=pipeline),
        MatchItemsStage(pipeline=pipeline),
        CorrelateItemsStage(pipeline=pipeline),
        WriteOutputsStage(pipeline=pipeline),
    )
    configured_stages = tuple(
        stage.configured(pipeline_type=pipeline.pipeline_type)
        for stage in stages
    )
    return pipeline.build_stage_chain(stages=configured_stages)
