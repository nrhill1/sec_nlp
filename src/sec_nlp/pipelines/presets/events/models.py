# src/sec_nlp/pipelines/presets/events/models.py
"""Data models for the events timeline pipeline."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.pipelines import BasePipelineResult
from sec_nlp.types import JsonValue


class EventHeadline(BaseModel):
    """Headline linked to a detected filing event."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    url: str
    source: str
    published_at: str | None = None
    published_date: str | None = None


class EventImpact(BaseModel):
    """Market-impact metrics for a detected event."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    car_5d: float | None = None
    car_30d: float | None = None
    volume_spike: float | None = None
    t_stat: float | None = None
    p_value: float | None = None
    significant: bool = False


class DetectedEvent(BaseModel):
    """Detected and optionally enriched corporate event."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    event_type: str
    event_date: str
    filing_accession: str
    filing_form: str = "8-K"
    filing_items: list[str] = Field(default_factory=list)
    entity_mentions: list[str] = Field(default_factory=list)
    text_snippet: str | None = None
    source_file: str | None = None

    headlines: list[EventHeadline] = Field(default_factory=list)
    impact: EventImpact | None = None


class EventsResult(BasePipelineResult):
    """Result model for the events pipeline."""

    pipeline_type: ClassVar[Literal["events"]] = "events"

    model_config = ConfigDict(frozen=True, extra="ignore")

    symbols_processed: int = Field(
        default=0,
        description="Number of symbols processed by the pipeline.",
    )
    events_detected: int = 0
    events_scored: int = 0
    headlines_linked: int = 0

    def summary_fields(self) -> dict[str, JsonValue]:
        fields: dict[str, JsonValue] = {}
        fields.update(self.base_summary_fields())
        fields["symbols_processed"] = self.symbols_processed
        fields["events_detected"] = self.events_detected
        fields["events_scored"] = self.events_scored
        fields["headlines_linked"] = self.headlines_linked
        return fields
