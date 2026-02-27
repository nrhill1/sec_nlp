# src/sec_nlp/pipelines/presets/events/run_stages.py
"""Runnable stage helpers for events pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.runnables import RunnableLambda
from rich.progress import Progress, TaskID

from .models import DetectedEvent
from .steps import (
    enrich_events_with_news,
    scan_events_for_symbol,
    score_event_impacts,
)

if TYPE_CHECKING:
    from .pipeline import EventsPipeline


@dataclass(slots=True)
class EventsRunState:
    """Mutable in-process state shared across events runnable stages."""

    symbol: str
    progress: Progress | None
    phase_task: TaskID | None
    scanned_events: list[DetectedEvent] = field(default_factory=list)
    enriched_events: list[DetectedEvent] = field(default_factory=list)
    scored_events: list[DetectedEvent] = field(default_factory=list)
    downloaded: int = 0
    filings_scanned: int = 0
    scored_count: int = 0
    headlines_linked: int = 0
    outputs: list[Path] = field(default_factory=list)
    metadata: dict[str, int | float | str | None] = field(default_factory=dict)


def create_initial_events_state(
    *,
    symbol: str,
    progress: Progress | None,
    phase_task: TaskID | None,
) -> EventsRunState:
    """Create initial mutable state for events runnable stage execution."""
    return EventsRunState(
        symbol=symbol,
        progress=progress,
        phase_task=phase_task,
    )


@dataclass(slots=True)
class EventsStageRunner:
    """Bound stage methods to avoid per-stage lambda/closure allocations."""

    pipeline: EventsPipeline

    def scan(self, state: EventsRunState) -> EventsRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Scanning",
        )
        state.scanned_events, state.downloaded, state.filings_scanned = (
            scan_events_for_symbol(
                symbol=state.symbol,
                settings=self.pipeline.config,
            )
        )
        return state

    def enrich(self, state: EventsRunState) -> EventsRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Enriching",
        )
        state.enriched_events, state.headlines_linked = enrich_events_with_news(
            symbol=state.symbol,
            events=state.scanned_events,
            settings=self.pipeline.config,
        )
        return state

    def score(self, state: EventsRunState) -> EventsRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Scoring",
        )
        state.scored_events, state.scored_count = score_event_impacts(
            symbol=state.symbol,
            events=state.enriched_events,
            settings=self.pipeline.config,
        )
        return state

    def write(self, state: EventsRunState) -> EventsRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Writing",
        )
        state.outputs = self.pipeline._write_outputs(
            symbol=state.symbol,
            events=state.scored_events,
        )
        state.metadata = {
            "downloaded": state.downloaded,
            "filings_scanned": state.filings_scanned,
            "events_detected": len(state.scored_events),
            "events_scored": state.scored_count,
            "headlines_linked": state.headlines_linked,
        }
        return state


def build_events_stage_runnables(
    pipeline: EventsPipeline,
) -> tuple[RunnableLambda[EventsRunState, EventsRunState], ...]:
    """Build deterministic events stage runnables."""
    runner = EventsStageRunner(pipeline)
    return pipeline.build_stage_runnables(
        named_stages=(
            ("scan_events", runner.scan),
            ("enrich_events", runner.enrich),
            ("score_events", runner.score),
            ("write_outputs", runner.write),
        )
    )
