# src/sec_nlp/pipelines/presets/news/io/formats/timeline.py
"""Writers for news timeline outputs."""

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

from ...models import NewsCorrelation, NewsHeadline, NewsTimelineEntry


class NewsTimelinePayload(BaseModel):
    """Root payload for JSON/YAML news timeline outputs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_timestamp: str
    run_short_id: int | None = None
    run_id: str
    run_short_id_display: str

    symbol: str
    topics: list[str] = Field(default_factory=list)
    items: list[NewsHeadline] = Field(default_factory=list)
    timeline: list[NewsTimelineEntry] = Field(default_factory=list)
    correlation: NewsCorrelation
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


TIMELINE_COLUMNS: tuple[str, ...] = (
    "symbol",
    "published_date",
    "published_at",
    "title",
    "url",
    "source",
    "relevance_score",
    "matched_topics",
    "matched_keywords",
    "nearest_filing_date",
    "nearest_filing_form",
    "nearest_filing_accession",
    "market_close",
    "market_return",
    "snippet",
)


def write_news_timeline_csv(
    path: Path,
    headlines: list[NewsHeadline],
    *,
    header_fields: Mapping[str, JsonValue] | None = None,
) -> None:
    """Write flattened headline rows for timeline analysis."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        write_csv_metadata_comments(handle, header_fields)
        writer = csv.DictWriter(handle, fieldnames=list(TIMELINE_COLUMNS))
        writer.writeheader()

        for item in headlines:
            payload = item.model_dump(mode="json")
            payload["matched_topics"] = ",".join(item.matched_topics)
            payload["matched_keywords"] = ",".join(item.matched_keywords)
            row = {column: payload.get(column) for column in TIMELINE_COLUMNS}
            writer.writerow(row)


def write_news_timeline_json(path, payload: NewsTimelinePayload) -> None:
    """Write news timeline payload to JSON."""
    write_json(path, payload, exclude_none=True)


def write_news_timeline_yaml(path, payload: NewsTimelinePayload) -> None:
    """Write news timeline payload to YAML."""
    write_yaml(path, payload, exclude_none=True, sort_keys=False)
