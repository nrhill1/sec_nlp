# src/sec_nlp/app/workspace/pulse_models.py
"""Define immutable daily review results shared by terminal and command clients.

Pulse acknowledgement is independent from reading a filing. These records carry
stable evidence identities, explicit research schedules, and provider outcomes
without requiring terminal or native provider imports.
"""

from datetime import UTC, date, datetime
from typing import Literal, Self
from uuid import uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from sec_nlp.app.pulse.models import MarketObservation, SourceStatus


class PulseFilters(BaseModel):
    """Select cached activity without triggering retrieval.

    Focused activity follows current watchlist mappings, topic phrases, and saved
    scan evidence. New means not explicitly acknowledged by the user.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    scope: Literal["focused", "all"] = Field(
        default="focused", description="Relevance scope."
    )
    new_only: bool = Field(
        default=True, description="Restrict to unreviewed evidence."
    )
    symbol: str = Field(default="", description="Exact symbol filter.")
    topic: str = Field(
        default="", description="Exact topic or saved scan name."
    )
    source: str = Field(
        default="", description="Exact publisher or discovery source."
    )
    form: str = Field(
        default="", description="Exact SEC form, including amendment suffix."
    )


class PulseItem(BaseModel):
    """Describe one durable piece of evidence in the daily activity feed.

    Source dates and local discovery time have distinct fields. Reasons expose
    deterministic associations and never imply that a filing party is its issuer.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    identity: str = Field(
        description="Stable filing or canonical headline identity."
    )
    kind: Literal["filing", "news"] = Field(description="Evidence family.")
    title: str = Field(description="Readable evidence label.")
    source: str = Field(description="Publisher or discovery provider.")
    url: str = Field(description="Original source URL.")
    discovered_at: AwareDatetime = Field(
        description="First local discovery time."
    )
    published_at: AwareDatetime | None = Field(
        default=None, description="Source publication or acceptance time."
    )
    filing_date: date | None = Field(
        default=None, description="Declared SEC filing date."
    )
    symbols: tuple[str, ...] = Field(
        default=(), description="Current matched symbols."
    )
    topics: tuple[str, ...] = Field(
        default=(), description="Current topics and saved scans."
    )
    reasons: tuple[str, ...] = Field(
        default=(), description="Visible reasons for relevance."
    )
    reviewed: bool = Field(
        default=False, description="Explicit acknowledgement state."
    )
    accession_number: str | None = Field(
        default=None, description="Canonical filing identity when applicable."
    )


class PulsePage(BaseModel):
    """Return one bounded activity page and its continuation cursor.

    A cursor points after the final visible discovery key; it does not depend on
    offsets that shift when refresh inserts new evidence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    items: tuple[PulseItem, ...] = Field(
        default=(), description="Visible activity rows."
    )
    next_cursor: str | None = Field(
        default=None, description="Opaque keyset continuation."
    )


class SymbolMapping(BaseModel):
    """Preserve a provider-declared ticker association and its provenance.

    Stale mappings remain available after a failed refresh, with the uncertainty
    visible in filing match reasons. Unsupported assets need no SEC association.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    symbol: str = Field(description="Normalized watched symbol.")
    cik: str = Field(
        pattern=r"^\d{10}$", description="SEC registry entity identifier."
    )
    name: str = Field(default="", description="Registry company name.")
    source_url: str = Field(
        default="https://www.sec.gov/files/company_tickers.json",
        description="Registry source URL.",
    )
    checked_at: AwareDatetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Latest registry check.",
    )
    stale: bool = Field(
        default=False,
        description="Whether the latest check failed to confirm this mapping.",
    )
    detail: str = Field(
        default="", description="Failure or registry explanation."
    )


class PulseSource(BaseModel):
    """Pair the latest provider attempt with its actual observation time.

    The result is independent of the latest usable quote, which remains visible
    across failed or empty attempts.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    status: SourceStatus = Field(description="Latest source outcome.")
    observed_at: AwareDatetime = Field(description="When retrieval completed.")


class ReviewAction(BaseModel):
    """Record an append-only decision about a thesis or journal review.

    Completion may close the schedule or supply a next date. Deferral requires a
    future date. Original journal entries remain immutable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    review_id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="Unique review history identifier.",
    )
    target_kind: Literal["watchlist", "journal"] = Field(
        description="Reviewed object category."
    )
    target_id: str = Field(
        description="Symbol or immutable journal identifier."
    )
    action: Literal["complete", "defer"] = Field(description="Review decision.")
    note: str = Field(default="", description="User-authored completion note.")
    next_review_on: date | None = Field(
        default=None, description="Next planned review, or closed schedule."
    )
    created_at: AwareDatetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Decision timestamp.",
    )

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        """Require a future deferral date and a written completion record.

        Raises:
            ValueError: If deferral has no future date or completion has no note.
        """
        if self.action == "defer" and (
            self.next_review_on is None
            or self.next_review_on <= self.created_at.date()
        ):
            raise ValueError("Deferral requires a future review date")
        if self.action == "complete" and not self.note.strip():
            raise ValueError("Completing a review requires a note")
        return self


class DueReview(BaseModel):
    """Expose a scheduled thesis or note with its effective next review date.

    Later review actions override the original date without rewriting evidence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    target_kind: Literal["watchlist", "journal"] = Field(
        description="Review target category."
    )
    target_id: str = Field(description="Stable target identity.")
    symbol: str | None = Field(
        default=None, description="Related watched symbol."
    )
    title: str = Field(description="Thesis label or journal observation.")
    review_on: date = Field(description="Effective scheduled review date.")
    thesis: str = Field(default="", description="User-authored hypothesis.")
    invalidation: str = Field(
        default="", description="Evidence that challenges the hypothesis."
    )


class PulseOverview(BaseModel):
    """Return compact cached context for the current profile.

    Market evidence, provider outcomes, mappings, and due research remain distinct
    so partial refreshes cannot make stale observations appear current.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    market: tuple[MarketObservation, ...] = Field(
        default=(), description="Latest usable quote per current symbol."
    )
    sources: tuple[PulseSource, ...] = Field(
        default=(), description="Latest provider outcomes."
    )
    mappings: tuple[SymbolMapping, ...] = Field(
        default=(), description="Current watchlist registry associations."
    )
    due_reviews: tuple[DueReview, ...] = Field(
        default=(), description="Theses and journal entries due today."
    )


class RefreshProgress(BaseModel):
    """Report source completion without library console output.

    Clients may render progress independently from durable source outcomes.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    completed: int = Field(ge=0, description="Completed source count.")
    total: int = Field(ge=0, description="Requested source count.")
    source: str = Field(description="Source that just completed.")
    status: Literal["ok", "empty", "error", "cancelled"] = Field(
        description="Source outcome."
    )


class ScanMatch(BaseModel):
    """Preserve the association between a saved scan and its selected evidence.

    The association survives later scan runs and carries explicit user-selected
    research provenance into workspace exports.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    scan_id: str = Field(description="Saved query identifier.")
    accession_number: str = Field(description="Matched filing accession.")


class PulseState(BaseModel):
    """Export durable review state and provenance alongside portable evidence.

    Activity rows preserve their stable identities so acknowledgements can be
    restored without deriving identity from mutable headline titles.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    activity: tuple[PulseItem, ...] = Field(
        default=(), description="All retained activity and review states."
    )
    reviews: tuple[ReviewAction, ...] = Field(
        default=(), description="Append-only research review history."
    )
    mappings: tuple[SymbolMapping, ...] = Field(
        default=(),
        description="Registry associations including removed symbols.",
    )
    market: tuple[MarketObservation, ...] = Field(
        default=(), description="Latest successful live market evidence."
    )
    sources: tuple[PulseSource, ...] = Field(
        default=(), description="Latest live provider outcomes."
    )
    scan_matches: tuple[ScanMatch, ...] = Field(
        default=(), description="Saved scan evidence associations."
    )
