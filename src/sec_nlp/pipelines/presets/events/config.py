# src/sec_nlp/pipelines/presets/events/config.py
"""Config model for the events timeline pipeline."""

from __future__ import annotations

from datetime import date, timedelta
from typing import ClassVar, Literal

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.pipelines.base.config import BasePipelineSettings


class EventsSettings(BasePipelineSettings):
    """Configuration for event detection and timeline scoring."""

    model_config = SettingsConfigDict(env_prefix="SEC_NLP_EVENTS_")

    pipeline_type: ClassVar[Literal["events"]] = "events"

    mode: FilingMode = Field(
        default=FilingMode.current,
        description="Filing mode for event extraction (8-K/6-K current reports).",
    )
    forms: list[str] | None = Field(
        default_factory=lambda: ["8-K", "6-K"],
        description="SEC forms to include for event extraction.",
    )
    lookback_years: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Lookback horizon in years when explicit dates are omitted.",
    )
    limit: int | None = Field(
        default=40,
        ge=1,
        description="Maximum number of filings to scan per symbol.",
    )
    event_types: list[str] = Field(
        default_factory=list,
        description="Optional event-type filters (e.g., merger, restatement, executive).",
    )
    pre_window_days: int = Field(
        default=5,
        ge=0,
        le=30,
        description="Event-study pre window in calendar days.",
    )
    post_window_days: int = Field(
        default=30,
        ge=1,
        le=180,
        description="Event-study post window in calendar days.",
    )
    news_window_days: int = Field(
        default=3,
        ge=0,
        le=30,
        description="News enrichment window around each event date (+/- N days).",
    )
    max_headlines_per_event: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of linked headlines to keep per event.",
    )
    significance_threshold: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="P-value threshold for significance labeling.",
    )
    benchmark_symbol: str = Field(
        default="SPY",
        description="Benchmark ticker used for event-study scoring.",
    )
    include_news_context: bool = Field(
        default=True,
        description="Enrich detected events with surrounding headlines.",
    )
    include_market_context: bool = Field(
        default=True,
        description="Score events with market impact metrics.",
    )
    output_format: Literal["csv", "json", "yaml", "all"] = Field(
        default="json",
        description="Output format for event timeline artifacts.",
    )

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: FilingMode) -> FilingMode:
        if value != FilingMode.current:
            raise ValueError(
                "Events pipeline only supports current filing mode (8-K/6-K)."
            )
        return value

    @field_validator("forms", mode="before")
    @classmethod
    def validate_forms(cls, value: list[str] | str | None) -> list[str] | None:
        if value is None:
            return ["8-K", "6-K"]
        if isinstance(value, str):
            value = [part for part in value.replace(",", " ").split() if part]

        normalized: list[str] = []
        seen: set[str] = set()
        for form in value:
            cleaned = form.strip().upper()
            if cleaned == "8K":
                cleaned = "8-K"
            elif cleaned == "6K":
                cleaned = "6-K"
            if cleaned not in {"8-K", "6-K"}:
                raise ValueError(
                    "Events pipeline only supports forms 8-K and 6-K."
                )
            if cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized or ["8-K", "6-K"]

    @field_validator("event_types", mode="before")
    @classmethod
    def normalize_event_types(cls, value: list[str] | str | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [part for part in value.replace(",", " ").split() if part]

        normalized: list[str] = []
        seen: set[str] = set()
        for raw in value:
            cleaned = raw.strip().lower().replace("-", "_").replace(" ", "_")
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized

    @field_validator("benchmark_symbol", mode="before")
    @classmethod
    def normalize_benchmark(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("benchmark_symbol cannot be empty")
        return cleaned

    @property
    def effective_event_date_range(self) -> tuple[date, date]:
        """Return date range for event scanning."""
        if self.start_date is not None or self.end_date is not None:
            return self.date_range
        end_date = date.today()
        start_date = end_date - timedelta(days=365 * self.lookback_years)
        return start_date, end_date

    def pipeline_label(self) -> str:
        return "Events"
