# src/sec_nlp/core/edgar/filing_models.py
"""Represent accession-based filing metadata independently from downloaded text.

Entity roles preserve multiple SEC listings of the same submission. Publication
coverage belongs to the workspace; these frozen records describe evidence and
on-demand documents without marking anything read or advancing checkpoints.
"""

import re
from datetime import date
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
)


class FilingEntity(BaseModel):
    """Represent one entity associated with a submission and its SEC role."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    cik: str = Field(description="Ten-digit entity CIK from source metadata.")
    name: str = Field(default="", description="SEC entity display name.")
    role: str = Field(
        default="unknown",
        description="Issuer, reporting owner, subject, or filer role.",
    )

    @field_validator("cik")
    @classmethod
    def validate_cik(cls, value: str) -> str:
        """Require an explicit numeric CIK and normalize leading zeros."""
        if not re.fullmatch(r"\d{1,10}", value.strip()) or int(value) == 0:
            raise ValueError("CIK must contain 1–10 digits and be nonzero")
        return value.strip().zfill(10)


class FilingRecord(BaseModel):
    """Represent a unique SEC accession with all observed entity associations."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    accession_number: str = Field(
        pattern=r"^\d{10}-\d{2}-\d{6}$",
        description="Canonical submission identity.",
    )
    entities: tuple[FilingEntity, ...] = Field(
        default=(), description="Associated issuers and filing parties."
    )
    form_type: str = Field(
        description="Exact SEC form including amendment suffix."
    )
    filed_date: date | None = Field(
        default=None,
        description="Official filing date, not inferred acceptance date.",
    )
    accepted_at: AwareDatetime | None = Field(
        default=None,
        description="Source-provided acceptance timestamp, never a feed update.",
    )
    filing_url: HttpUrl = Field(description="SEC filing-detail page.")
    submission_url: HttpUrl = Field(description="Complete submission text URL.")


class FilingPage(BaseModel):
    """Represent one feed page without claiming complete market coverage."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    filings: tuple[FilingRecord, ...] = Field(
        description="Accession-deduplicated records on this page."
    )
    next_start: int | None = Field(
        default=None,
        description="Next ephemeral feed offset, if another page may exist.",
    )
    raw_entries: int = Field(
        default=0, description="Feed entries before entity-role merging."
    )


class IndexArtifact(BaseModel):
    """Describe a published daily index or requested quarterly index artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    url: HttpUrl = Field(description="Exact SEC index URL.")
    year: int = Field(ge=1994, le=9999, description="Index calendar year.")
    quarter: int = Field(ge=1, le=4, description="Index calendar quarter.")
    kind: Literal["daily", "full"] = Field(description="Index coverage family.")
    published_date: date | None = Field(
        default=None,
        description="Daily index date; absent for quarter-wide indexes.",
    )


class FilingDocument(BaseModel):
    """Describe one selectable document from a filing's official manifest."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    filename: str = Field(
        description="Provider document filename within the accession."
    )
    url: HttpUrl = Field(description="Exact SEC document URL.")
    sequence: int | None = Field(
        default=None, description="Provider document sequence when numeric."
    )
    description: str = Field(
        default="", description="Provider document description."
    )
    document_type: str = Field(
        default="", description="Exact provider form or exhibit type."
    )
    size_bytes: int | None = Field(
        default=None, ge=0, description="Declared byte size when available."
    )


class FilingManifest(BaseModel):
    """Represent the document choices available when a filing is opened."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    filing: FilingRecord = Field(
        description="Parent accession and entity metadata."
    )
    documents: tuple[FilingDocument, ...] = Field(
        description="Document table entries in provider order."
    )


class DocumentContent(BaseModel):
    """Represent full readable document text with optional original HTML."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    document: FilingDocument = Field(
        description="Source document and provenance."
    )
    text: str = Field(
        description="Complete extracted text, without analysis chunk truncation."
    )
    html: str | None = Field(
        default=None,
        description="Original HTML when the document contains markup.",
    )
