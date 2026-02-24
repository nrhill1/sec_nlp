# src/sec_nlp/pipelines/presets/events/io/formats/timeline.py
"""Writers for events timeline outputs."""

from __future__ import annotations

import csv
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.pipelines.output_io import (
    write_csv_metadata_comments,
    write_json,
    write_yaml,
)
from sec_nlp.types import JsonValue

from ...models import DetectedEvent


class EventsTimelinePayload(BaseModel):
    """Root payload for JSON/YAML events timeline outputs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_timestamp: str
    run_short_id: int | None = None
    run_id: str
    run_short_id_display: str

    symbol: str
    events: list[DetectedEvent] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


TIMELINE_COLUMNS: tuple[str, ...] = (
    "symbol",
    "event_date",
    "event_type",
    "filing_accession",
    "filing_form",
    "filing_items",
    "headline_count",
    "car_5d",
    "car_30d",
    "volume_spike",
    "p_value",
    "significant",
    "text_snippet",
    "source_file",
)


def write_events_timeline_csv(
    path: Path,
    events: list[DetectedEvent],
    *,
    header_fields: Mapping[str, JsonValue] | None = None,
) -> None:
    """Write flattened event rows for timeline analysis."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        write_csv_metadata_comments(handle, header_fields)
        writer = csv.DictWriter(handle, fieldnames=list(TIMELINE_COLUMNS))
        writer.writeheader()

        for event in events:
            row = {
                "symbol": event.symbol,
                "event_date": event.event_date,
                "event_type": event.event_type,
                "filing_accession": event.filing_accession,
                "filing_form": event.filing_form,
                "filing_items": ",".join(event.filing_items),
                "headline_count": len(event.headlines),
                "car_5d": event.impact.car_5d if event.impact else None,
                "car_30d": event.impact.car_30d if event.impact else None,
                "volume_spike": event.impact.volume_spike
                if event.impact
                else None,
                "p_value": event.impact.p_value if event.impact else None,
                "significant": event.impact.significant
                if event.impact
                else False,
                "text_snippet": event.text_snippet,
                "source_file": event.source_file,
            }
            writer.writerow(row)


def write_events_timeline_json(
    path: Path, payload: EventsTimelinePayload
) -> None:
    """Write events timeline payload to JSON."""
    write_json(path, payload, exclude_none=True)


def write_events_timeline_yaml(
    path: Path, payload: EventsTimelinePayload
) -> None:
    """Write events timeline payload to YAML."""
    write_yaml(path, payload, exclude_none=True, sort_keys=False)
