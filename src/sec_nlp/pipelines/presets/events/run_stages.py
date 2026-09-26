# src/sec_nlp/pipelines/presets/events/run_stages.py
"""Ordered specialist steps for events pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field
from rich.progress import Progress, TaskID

from sec_nlp.pipelines.base.stages import PipelineStage, StageSequence
from sec_nlp.pipelines.presets.events.steps.enrich import (
    enrich_events_with_news,
)
from sec_nlp.pipelines.presets.events.steps.scan import scan_events_for_symbol
from sec_nlp.pipelines.presets.events.steps.score import score_event_impacts

from .models import DetectedEvent

if TYPE_CHECKING:
    from .pipeline import EventsPipeline


@dataclass(slots=True)
class EventsRunState:
    """In-place state carrier for events stages from scan to output persistence."""

    runtime: EventsPipeline
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


class ScanEventsStage(PipelineStage[EventsRunState]):
    """Ingress stage that scans filings and materializes candidate event records."""

    name: str = Field(default="scan_events")

    def _run(self, state: EventsRunState) -> EventsRunState:
        """Execute this events stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Scanning",
        )
        state.scanned_events, state.downloaded, state.filings_scanned = (
            scan_events_for_symbol(
                symbol=state.symbol,
                settings=state.runtime.config,
            )
        )
        return state


class EnrichEventsStage(PipelineStage[EventsRunState]):
    """Enrichment stage that links related news context onto scanned event records."""

    name: str = Field(default="enrich_events")

    def _run(self, state: EventsRunState) -> EventsRunState:
        """Execute this events stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Enriching",
        )
        state.enriched_events, state.headlines_linked = enrich_events_with_news(
            symbol=state.symbol,
            events=state.scanned_events,
            settings=state.runtime.config,
        )
        return state


class ScoreEventsStage(PipelineStage[EventsRunState]):
    """Scoring stage that computes impact metrics for enriched event records."""

    name: str = Field(default="score_events")

    def _run(self, state: EventsRunState) -> EventsRunState:
        """Execute this events stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Scoring",
        )
        state.scored_events, state.scored_count = score_event_impacts(
            symbol=state.symbol,
            events=state.enriched_events,
            settings=state.runtime.config,
        )
        return state


class WriteEventsOutputsStage(PipelineStage[EventsRunState]):
    """Egress stage that persists event artifacts and run metadata."""

    name: str = Field(default="write_outputs")

    def _run(self, state: EventsRunState) -> EventsRunState:
        """Execute this events stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.symbol,
            "Writing",
        )
        state.outputs = state.runtime._write_outputs(
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


_EVENTS_STAGES: tuple[PipelineStage[EventsRunState], ...] = (
    ScanEventsStage(),
    EnrichEventsStage(),
    ScoreEventsStage(),
    WriteEventsOutputsStage(),
)


def build_events_stage_chain(
    pipeline: EventsPipeline,
) -> StageSequence[EventsRunState]:
    """Build deterministic events stage chain."""
    return pipeline.build_configured_stage_chain(stages=_EVENTS_STAGES)
