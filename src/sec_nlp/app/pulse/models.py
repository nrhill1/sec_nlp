# src/sec_nlp/app/pulse/models.py
"""Typed configuration, evidence, and journal records for Pulse workspaces.

The workspace keeps user-authored hypotheses separate from retrieved market
observations. Frozen records support reproducible reports and offline review
without inheriting filing, embedding, or model configuration.
"""

import re
from datetime import date
from typing import Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


def normalize_symbol(value: str) -> str:
    """Return a normalized market symbol with no paths or shell syntax.

    Raises:
        ValueError: If the value is not a supported ticker symbol.
    """
    symbol = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=\-]{0,19}", symbol):
        raise ValueError("Use a ticker such as AAPL, BRK-B, ^GSPC, or BTC-USD")
    return symbol


class WatchItem(BaseModel):
    """Represent one research target and the user's investment hypothesis.

    Aliases match company names in headlines. Thesis and invalidation text
    are authored by the user and never inferred from price movement.
    """

    model_config = ConfigDict(
        frozen=True, extra="forbid", str_strip_whitespace=True
    )

    symbol: str = Field(description="Market symbol to observe.")
    name: str = Field(default="", description="Readable company or asset name.")
    aliases: tuple[str, ...] = Field(
        default=(), description="Additional headline search phrases."
    )
    thesis: str = Field(
        default="", description="User-authored reason for following this asset."
    )
    invalidation: str = Field(
        default="", description="Evidence that would challenge the thesis."
    )
    review_on: date | None = Field(
        default=None, description="Next planned thesis review date."
    )

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        """Normalize symbols so repeated watchlist entries can be rejected."""
        return normalize_symbol(value)


class Theme(BaseModel):
    """Represent a current-events topic and a question to investigate.

    Keywords link observed headlines to the topic; the research question
    preserves the distinction between evidence and interpretation.
    """

    model_config = ConfigDict(
        frozen=True, extra="forbid", str_strip_whitespace=True
    )

    name: str = Field(min_length=1, description="Topic label.")
    keywords: tuple[str, ...] = Field(
        min_length=1, description="Phrases to match in headlines."
    )
    question: str = Field(
        default="",
        description="Question to revisit when matching news appears.",
    )


class Feed(BaseModel):
    """Describe one independently fetched source of current-events evidence.

    An optional symbol scope labels company-specific feeds. General feeds
    remain visible even when their headlines do not mention a watchlist item.
    """

    model_config = ConfigDict(
        frozen=True, extra="forbid", str_strip_whitespace=True
    )

    name: str = Field(
        min_length=1, description="Source name displayed in reports."
    )
    url: HttpUrl = Field(description="HTTP or HTTPS feed endpoint.")
    feed_type: Literal["rss", "atom", "json_noauth"] = Field(
        default="rss", description="Native newswatch feed parser."
    )
    symbols: tuple[str, ...] = Field(
        default=(), description="Symbols explicitly covered by the feed."
    )

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Normalize explicit source scope without duplicate symbols."""
        return tuple(dict.fromkeys(normalize_symbol(value) for value in values))


class PulseSettings(BaseModel):
    """Configure a portable, local market observation workspace.

    The configuration defines research goals, sources, and refresh windows.
    It contains no order execution, account credentials, or asset allocations.
    """

    model_config = ConfigDict(
        frozen=True, extra="forbid", str_strip_whitespace=True
    )

    schema_version: Literal[1] = Field(
        default=1, description="Workspace format version."
    )
    name: str = Field(
        default="Pulse", min_length=1, description="Workspace title."
    )
    goal: str = Field(
        default="Observe market changes and revisit investment theses using evidence.",
        description="User-defined investing or observation goal.",
    )
    watchlist: tuple[WatchItem, ...] = Field(
        default=(),
        description="Assets to follow; an empty list supports macro-only briefs.",
    )
    benchmarks: tuple[str, ...] = Field(
        default=("SPY",),
        description="Reference assets, not suggested holdings.",
    )
    themes: tuple[Theme, ...] = Field(
        default=(), description="Current-events research themes."
    )
    feeds: tuple[Feed, ...] = Field(
        default=(), description="Current-events sources fetched independently."
    )
    company_feeds: bool = Field(
        default=True,
        description="Add Yahoo Finance RSS for each watched symbol.",
    )
    lookback_days: int = Field(
        default=7,
        ge=1,
        le=90,
        description="Calendar-day headline window; feeds may retain less history.",
    )
    market_days: int = Field(
        default=35,
        ge=10,
        le=365,
        description="Calendar-day quote retrieval window.",
    )
    stale_after_days: int = Field(
        default=4,
        ge=1,
        le=30,
        description="Calendar days before a quote is marked stale.",
    )
    max_headlines: int = Field(
        default=60,
        ge=1,
        le=500,
        description="Maximum deduplicated headlines in a brief.",
    )
    move_threshold_pct: float = Field(
        default=3.0,
        gt=0,
        le=100,
        allow_inf_nan=False,
        description="Absolute one-session move that prompts research.",
    )
    user_agent: str = Field(
        default="sec-nlp pulse observer",
        min_length=1,
        description="HTTP identity; add your contact email for SEC feeds.",
    )

    @field_validator("benchmarks")
    @classmethod
    def validate_benchmarks(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Normalize reference symbols and remove duplicates."""
        return tuple(dict.fromkeys(normalize_symbol(value) for value in values))

    @model_validator(mode="after")
    def validate_unique_entries(self) -> Self:
        """Reject duplicate watchlist symbols, feed names, and theme labels.

        Raises:
            ValueError: If an entry would make report attribution ambiguous.
        """
        groups = (
            ("watchlist symbol", tuple(item.symbol for item in self.watchlist)),
            ("feed name", tuple(feed.name.casefold() for feed in self.feeds)),
            (
                "theme name",
                tuple(theme.name.casefold() for theme in self.themes),
            ),
        )
        for label, values in groups:
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate {label}")
        return self


class MarketObservation(BaseModel):
    """Represent dated price evidence and explicitly bounded return windows.

    Returns use adjusted closes across available sessions. The displayed
    close is the unadjusted provider close; a current session can still be
    provisional. Missing history remains missing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(description="Observed market symbol.")
    quote_date: date | None = Field(
        default=None, description="UTC date of the latest available quote."
    )
    close: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Latest unadjusted provider close in the listing currency; the current session may be incomplete.",
    )
    change_1d_pct: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Adjusted-close change over one observed session.",
    )
    change_5d_pct: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Adjusted-close change over five observed sessions.",
    )
    observations: int = Field(
        default=0, ge=0, description="Number of usable observed sessions."
    )
    stale: bool = Field(
        default=False,
        description="Whether the last quote exceeds the configured age limit.",
    )
    source_url: HttpUrl = Field(
        description="Provider page for the observed asset."
    )


class Headline(BaseModel):
    """Represent sourced headline evidence with deterministic relevance labels.

    Labels are phrase matches or explicit feed scope, not causal claims.
    Undated evidence is retained with its missing date visible.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(description="Provider headline text.")
    url: HttpUrl = Field(description="Source article URL.")
    source: str = Field(description="Configured source name.")
    published_at: AwareDatetime | None = Field(
        default=None,
        description="Normalized publication timestamp, when available.",
    )
    symbols: tuple[str, ...] = Field(
        default=(), description="Matched watchlist symbols."
    )
    themes: tuple[str, ...] = Field(
        default=(), description="Matched current-events topics."
    )
    is_new: bool = Field(
        default=True,
        description="Whether absent from the preceding compatible saved brief.",
    )


class SourceStatus(BaseModel):
    """Record data availability for one feed or market symbol.

    Independent statuses keep a partial report from implying that every
    requested source was retrieved successfully.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(description="Feed or market symbol identifier.")
    kind: Literal["news", "market"] = Field(description="Evidence category.")
    status: Literal["ok", "empty", "error"] = Field(
        description="Retrieval outcome."
    )
    detail: str = Field(
        default="", description="Availability or failure explanation."
    )
    records: int = Field(
        default=0, ge=0, description="Number of usable retrieved records."
    )


class JournalEntry(BaseModel):
    """Preserve a user's observation, hypothesis, and next review date.

    Entries are individually saved for an append-only research history.
    Evidence URLs and invalidation criteria make later review concrete.
    """

    model_config = ConfigDict(
        frozen=True, extra="forbid", str_strip_whitespace=True
    )

    entry_id: str = Field(
        pattern=r"^[a-f0-9]{32}$",
        description="Unique immutable journal identifier.",
    )
    created_at: AwareDatetime = Field(
        description="Timestamp when the note was saved."
    )
    symbol: str | None = Field(
        default=None, description="Optional watchlist symbol."
    )
    observation: str = Field(
        min_length=1, description="User-authored observation."
    )
    thesis: str = Field(
        default="", description="Interpretation to test against later evidence."
    )
    invalidation: str = Field(
        default="", description="What would contradict the hypothesis."
    )
    review_on: date | None = Field(
        default=None, description="Date to revisit this entry."
    )
    sources: tuple[HttpUrl, ...] = Field(
        default=(), description="Supporting evidence links."
    )

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str | None) -> str | None:
        """Normalize an optional asset reference for journal filtering."""
        return normalize_symbol(value) if value is not None else None


class Brief(BaseModel):
    """Capture a reproducible Pulse report and its exact configuration.

    The snapshot supports offline rendering and comparing successive
    reports without refetching sources or running an LLM.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = Field(
        default=1, description="Report schema version."
    )
    brief_id: str = Field(
        pattern=r"^[a-f0-9]{32}$", description="Unique report identifier."
    )
    generated_at: AwareDatetime = Field(description="UTC report creation time.")
    settings: PulseSettings = Field(
        description="Configuration used for this report."
    )
    demo: bool = Field(
        default=False, description="True for synthetic demonstration evidence."
    )
    previous_brief_id: str | None = Field(
        default=None,
        description="Prior compatible snapshot used for headline comparison.",
    )
    market: tuple[MarketObservation, ...] = Field(
        default=(), description="Watchlist and benchmark price observations."
    )
    headlines: tuple[Headline, ...] = Field(
        default=(), description="Deduplicated, dated current-events evidence."
    )
    sources: tuple[SourceStatus, ...] = Field(
        default=(), description="Per-source coverage and failure status."
    )
    journal: tuple[JournalEntry, ...] = Field(
        default=(), description="Research journal at report generation time."
    )
    prompts: tuple[str, ...] = Field(
        default=(),
        description="Evidence-driven research checks, not trading recommendations.",
    )
