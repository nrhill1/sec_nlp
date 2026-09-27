# src/sec_nlp/app/workspace/models.py
"""Define durable research state shared by the terminal and workspace ledger.

These records describe user intent, discovery coverage, and local state without
depending on an AI model, vector service, or terminal implementation.
"""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, Self
from uuid import uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from sec_nlp.core.edgar.filing_models import FilingRecord


class ScanSpec(BaseModel):
    """Describe a saved SEC discovery query and its explicit date bounds.

    Saved scans retain user-selected entities and forms across refreshes; they
    are configuration records rather than scheduled background processes.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scan_id: str = Field(
        default_factory=lambda: uuid4().hex,
        min_length=1,
        description="Stable scan identifier.",
    )
    name: str = Field(min_length=1, description="User-facing scan name.")
    query: str = Field(default="", description="Full-text search expression.")
    symbols: tuple[str, ...] = Field(
        default=(), description="Ticker aliases selected by the user."
    )
    ciks: tuple[str, ...] = Field(
        default=(), description="Explicit SEC entity identifiers."
    )
    forms: tuple[str, ...] = Field(
        default=(), description="SEC form types; empty accepts all forms."
    )
    start_date: date | None = Field(
        default=None, description="Inclusive earliest filing date."
    )
    end_date: date | None = Field(
        default=None, description="Inclusive latest filing date."
    )
    enabled: bool = Field(
        default=True,
        description="Whether explicit execution of this scan is enabled.",
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum discovered filings per scan.",
    )
    max_documents: int = Field(
        default=20,
        ge=0,
        le=100,
        description="Maximum documents opened by an explicit scan run.",
    )

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        """Reject inverted date windows rather than silently returning no filings."""
        if (
            self.start_date
            and self.end_date
            and self.start_date > self.end_date
        ):
            raise ValueError("start_date must not follow end_date")
        return self


class InboxItem(BaseModel):
    """Join a canonical filing with persistent user review state.

    Discovery refreshes update evidence while preserving read and bookmark
    choices; first-seen and last-seen dates remain distinct.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    filing: FilingRecord = Field(description="Canonical accession record.")
    is_read: bool = Field(
        default=False, description="Whether the user has reviewed this filing."
    )
    bookmarked: bool = Field(
        default=False, description="Whether the user saved this filing."
    )
    first_seen_at: AwareDatetime = Field(
        description="First local discovery time."
    )
    last_seen_at: AwareDatetime = Field(
        description="Latest local discovery time."
    )
    source: str = Field(default="", description="Most recent discovery source.")
    source_withdrawn: bool = Field(
        default=False,
        description="Whether a reconciled index no longer lists this accession; preserved evidence remains available.",
    )


class SourceCheckpoint(BaseModel):
    """Retain retrieval progress and visible coverage for one source scope.

    An error records the latest attempt while retaining the last successful
    checkpoint, so interrupted pages cannot masquerade as complete coverage.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(min_length=1, description="Provider or source name.")
    scope: str = Field(default="", description="Query, scan, or entity scope.")
    cursor: str | None = Field(
        default=None,
        description="Provider continuation token or local watermark.",
    )
    checked_at: AwareDatetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Latest retrieval attempt.",
    )
    last_success_at: AwareDatetime | None = Field(
        default=None, description="Most recent complete retrieval."
    )
    status: Literal["complete", "partial", "error"] = Field(
        description="Coverage of the attempted retrieval."
    )
    detail: str = Field(
        default="", description="Coverage limits or failure explanation."
    )
    records: int = Field(default=0, ge=0, description="Observed record count.")
    pages: int = Field(
        default=0, ge=0, description="Successfully read page count."
    )
    artifact_url: str | None = Field(
        default=None, description="Exact index artifact retrieved."
    )
    content_hash: str | None = Field(
        default=None,
        description="Digest of successfully processed artifact contents.",
    )
    processed_at: AwareDatetime | None = Field(
        default=None,
        description="Time successful parsed contents entered the ledger.",
    )


class JobRecord(BaseModel):
    """Record local operation progress for terminal status and later review.

    Job history is independent of process lifetime and exposes interrupted or
    failed work without inventing a successful result.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: str = Field(
        default_factory=lambda: uuid4().hex,
        min_length=1,
        description="Stable operation identifier.",
    )
    kind: str = Field(min_length=1, description="Operation category.")
    status: Literal["pending", "running", "complete", "error", "cancelled"] = (
        Field(default="pending", description="Current operation outcome.")
    )
    message: str = Field(
        default="", description="Readable progress or failure detail."
    )
    created_at: AwareDatetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Operation creation time.",
    )
    updated_at: AwareDatetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Latest recorded status time.",
    )
    scan_id: str | None = Field(
        default=None, description="Saved scan associated with this operation."
    )


class CachePointer(BaseModel):
    """Locate preserved document content without copying large files into SQLite.

    External pointers support migration of existing download caches; workspace
    content can use the same record with a local owned file path.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(
        min_length=1, description="Stable document URL or migration identifier."
    )
    path: Path = Field(
        description="Absolute path to the existing cached file or directory."
    )
    accession_number: str | None = Field(
        default=None, description="Related filing accession when known."
    )
    media_type: str = Field(
        default="text/plain", description="Content media type."
    )
    external: bool = Field(
        default=False,
        description="Whether the workspace does not own the pointed-to data.",
    )


class MigrationResult(BaseModel):
    """Summarize an additive import of a preexisting investing workspace.

    Counts include newly imported records only; original files remain untouched
    and repeat runs do not replace newer workspace state.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Path = Field(description="Original workspace directory.")
    settings_imported: bool = Field(
        default=False,
        description="Whether the legacy configuration initialized the destination.",
    )
    notes_imported: int = Field(
        default=0, ge=0, description="New journal entries."
    )
    briefs_imported: int = Field(
        default=0, ge=0, description="New report snapshots."
    )
    cache_pointers_imported: int = Field(
        default=0,
        ge=0,
        description="New references to preserved download caches.",
    )
    recipes_imported: int = Field(
        default=0,
        ge=0,
        description="New validated copies of authored research jobs.",
    )
    recipe_paths: tuple[Path, ...] = Field(
        default=(),
        description="Imported recipe files usable with the research command.",
    )
    filings_imported: int = Field(
        default=0,
        ge=0,
        description="New SEC filings identified in legacy caches.",
    )
    documents_imported: int = Field(
        default=0,
        ge=0,
        description="New cached documents available for offline reading.",
    )
    warnings: tuple[str, ...] = Field(
        default=(),
        description="Preserved cache files that could not be identified safely.",
    )
