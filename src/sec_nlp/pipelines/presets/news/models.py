# src/sec_nlp/pipelines/presets/news/models.py
"""Data models for news monitoring outputs."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.pipelines.base.result import BasePipelineResult
from sec_nlp.types import JsonValue


class FilingEvent(BaseModel):
    """A filing event near a headline date."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    filing_date: str
    form_type: str
    accession_number: str


class NewsHeadline(BaseModel):
    """A normalized, scored headline in the pipeline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    title: str
    url: str
    source: str
    published_at: str | None = None
    published_date: str | None = None
    snippet: str | None = None
    matched_keywords: list[str] = Field(default_factory=list)
    matched_topics: list[str] = Field(default_factory=list)
    relevance_score: float = 0.0

    nearest_filing_date: str | None = None
    nearest_filing_form: str | None = None
    nearest_filing_accession: str | None = None

    market_close: float | None = None
    market_return: float | None = None


class NewsCluster(BaseModel):
    """A cluster of concentrated headline activity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start_date: str
    end_date: str
    headline_count: int


class NewsCorrelation(BaseModel):
    """Aggregate correlation metadata for a symbol run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    news_to_return_correlation: float | None = None
    days_compared: int = 0
    days_with_news: int = 0
    days_with_market_data: int = 0
    average_daily_headlines: float = 0.0
    filings_linked: int = 0
    clusters: list[NewsCluster] = Field(default_factory=list)


class NewsTimelineEntry(BaseModel):
    """Timeline row combining headlines, filing events, and market snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    date: str
    headline_count: int
    headlines: list[NewsHeadline] = Field(default_factory=list)
    filings: list[FilingEvent] = Field(default_factory=list)
    market_close: float | None = None
    market_return: float | None = None


class NewsResult(BasePipelineResult):
    """Result model for the news pipeline."""

    pipeline_type: ClassVar[Literal["news"]] = "news"

    model_config = ConfigDict(frozen=True, extra="ignore")

    symbols_processed: int = Field(
        default=0,
        description="Number of symbols processed by the pipeline.",
    )
    items_fetched: int = Field(
        default=0,
        description="Total headlines fetched before topic filtering.",
    )
    items_emitted: int = Field(
        default=0,
        description="Total headlines emitted after filtering.",
    )
    clusters_detected: int = Field(
        default=0,
        description="Total number of detected headline clusters.",
    )

    def summary_fields(self) -> dict[str, JsonValue]:
        fields: dict[str, JsonValue] = {}
        fields.update(self.base_summary_fields())
        fields["symbols_processed"] = self.symbols_processed
        fields["items_fetched"] = self.items_fetched
        fields["items_emitted"] = self.items_emitted
        fields["clusters_detected"] = self.clusters_detected
        return fields
