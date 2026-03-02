# src/sec_nlp/pipelines/presets/news/config.py
"""Config model for the news monitoring pipeline."""

from __future__ import annotations

from datetime import date, timedelta
from typing import ClassVar, Literal

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.pipelines.base.config import BasePipelineSettings


class NewsSettings(BasePipelineSettings):
    """Configuration for company-centric financial news monitoring."""

    model_config = SettingsConfigDict(env_prefix="SEC_NLP_NEWS_")

    pipeline_type: ClassVar[Literal["news"]] = "news"

    mode: FilingMode = Field(
        default=FilingMode.current,
        description="Default filing mode when forms are not explicitly set.",
    )
    forms: list[str] | None = Field(
        default_factory=lambda: ["8-K", "10-K", "10-Q"],
        description="Filing forms used when linking headlines to filings.",
    )
    topics: list[str] = Field(
        default_factory=list,
        description="Topic keywords to score and filter headlines.",
    )
    days: int = Field(
        default=90,
        ge=1,
        le=3650,
        description="Lookback window in days when start/end dates are not provided.",
    )
    feeds: list[str] = Field(
        default_factory=list,
        description=(
            "Optional custom feed definitions. Use URL or URL|TYPE|NAME where "
            "TYPE is rss or json_api."
        ),
    )
    min_relevance: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum topic relevance score required to keep a headline.",
    )
    require_symbol_match: bool = Field(
        default=True,
        description=(
            "Require headline text to include the target symbol in addition to topic matches."
        ),
    )
    max_results: int = Field(
        default=250,
        ge=1,
        le=5000,
        description="Maximum number of headlines to keep per symbol.",
    )
    rate_limit_secs: float = Field(
        default=0.15,
        ge=0.0,
        le=30.0,
        description="Delay between feed requests when fetching headlines.",
    )
    include_market_context: bool = Field(
        default=True,
        description="Fetch market data and compute news-volume/return correlation.",
    )
    filing_match_window_days: int = Field(
        default=7,
        ge=0,
        le=30,
        description="Max distance between headline date and filing date for linkage.",
    )
    cluster_threshold: int = Field(
        default=3,
        ge=2,
        le=100,
        description="Minimum headlines required to flag a news cluster.",
    )
    cluster_gap_days: int = Field(
        default=1,
        ge=0,
        le=14,
        description="Allowed day gap when grouping adjacent headlines into clusters.",
    )
    output_format: Literal["csv", "json", "yaml", "all"] = Field(
        default="json",
        description="Output file format to emit.",
    )

    @field_validator("topics", mode="before")
    @classmethod
    def normalize_topics(cls, value: list[str] | str | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [part for part in value.replace(",", " ").split() if part]

        normalized: list[str] = []
        for topic in value:
            cleaned = topic.strip()
            if cleaned:
                normalized.append(cleaned)
        return list(dict.fromkeys(normalized))

    @field_validator("forms", mode="before")
    @classmethod
    def normalize_news_forms(cls, value: list[str] | str | None) -> list[str]:
        if value is None:
            return ["8-K", "10-K", "10-Q"]
        if isinstance(value, str):
            value = [part for part in value.replace(",", " ").split() if part]

        normalized: list[str] = []
        for form in value:
            cleaned = form.strip().upper()
            if cleaned in ("10K", "10Q", "8K"):
                cleaned = f"{cleaned[:-1]}-{cleaned[-1]}"
            if cleaned:
                normalized.append(cleaned)
        return list(dict.fromkeys(normalized)) or ["8-K", "10-K", "10-Q"]

    @field_validator("feeds", mode="before")
    @classmethod
    def normalize_feeds(cls, value: list[str] | str | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [part for part in value.split(",") if part.strip()]

        normalized: list[str] = []
        for item in value:
            cleaned = item.strip()
            if cleaned:
                normalized.append(cleaned)
        return normalized

    @property
    def effective_news_date_range(self) -> tuple[date, date]:
        """Return the date range used for headline/filling correlation."""
        if self.start_date is not None or self.end_date is not None:
            return self.date_range
        end_date = date.today()
        start_date = end_date - timedelta(days=self.days)
        return start_date, end_date

    def pipeline_label(self) -> str:
        return "News"
