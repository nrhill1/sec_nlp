# src/sec_nlp/app/flows/contracts/events.py
"""Flow contracts for news/events/financial ownership signal handoff."""

from pydantic import BaseModel, ConfigDict, Field


class HeadlineBundle(BaseModel):
    """News-stage output envelope for headline-driven downstream enrichment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    upstream_pipeline: str = Field(
        default="news",
        description="Pipeline that generated this headline context.",
    )
    upstream_run_id: str = Field(
        description="Upstream run UUID for provenance.",
    )
    symbols: list[str] = Field(
        default_factory=list,
        description="Symbols represented by headlines.",
    )
    topics: list[str] = Field(
        default_factory=list,
        description="Configured topic scope from the news run.",
    )
    output_paths: list[str] = Field(
        default_factory=list,
        description="News output artifact paths.",
    )


class EventTimelineBundle(BaseModel):
    """Events-stage output envelope summarizing detected event sequences."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    upstream_pipeline: str = Field(
        default="events",
        description="Pipeline that generated this event timeline.",
    )
    upstream_run_id: str = Field(
        description="Upstream run UUID for provenance.",
    )
    symbols: list[str] = Field(
        default_factory=list,
        description="Symbol scope represented in the timeline.",
    )
    output_paths: list[str] = Field(
        default_factory=list,
        description="Timeline/summary output paths.",
    )
    events_detected: int = Field(
        default=0,
        description="Total detected events in the run result.",
    )


class FinancialStatementBundle(BaseModel):
    """Financials-stage handoff object for statement-level signal context."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    upstream_pipeline: str = Field(
        default="financials",
        description="Pipeline that generated this statement context.",
    )
    upstream_run_id: str = Field(
        description="Upstream run UUID for provenance.",
    )
    symbols: list[str] = Field(
        default_factory=list,
        description="Symbols represented in statement outputs.",
    )
    output_paths: list[str] = Field(
        default_factory=list,
        description="Financial statement output artifact paths.",
    )


class OwnershipSignalBundle(BaseModel):
    """Holdings/insider handoff object for ownership and activity context."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    upstream_pipeline: str = Field(
        description="Pipeline that generated this ownership signal.",
    )
    upstream_run_id: str = Field(
        description="Upstream run UUID for provenance.",
    )
    symbols: list[str] = Field(
        default_factory=list,
        description="Symbols represented by ownership signals.",
    )
    output_paths: list[str] = Field(
        default_factory=list,
        description="Ownership signal output artifact paths.",
    )
