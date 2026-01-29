# src/sec_nlp/core/edgar/efts_models.py
"""Data models for SEC EDGAR Full-Text Search (EFTS) API."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EFTSSortField(StrEnum):
    """Available sort fields for EFTS search."""

    filed = "filed"
    relevance = "score"


class EFTSSortOrder(StrEnum):
    """Sort order for EFTS search results."""

    asc = "asc"
    desc = "desc"


class EFTSSearchParams(BaseModel):
    """Parameters for EFTS search requests.

    Maps to the SEC EFTS API query parameters.
    See: https://efts.sec.gov/LATEST/search-index
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    query: str = Field(
        description="Full-text search query string",
    )
    forms: list[str] = Field(
        default_factory=list,
        description="Form types to filter (e.g., ['10-K', '10-Q', '8-K'])",
    )
    ciks: list[str] = Field(
        default_factory=list,
        description="CIK numbers to filter (10-digit padded)",
    )
    tickers: list[str] = Field(
        default_factory=list,
        description="Ticker symbols to filter",
    )
    start_date: date | None = Field(
        default=None,
        description="Start date for filing date range (inclusive)",
    )
    end_date: date | None = Field(
        default=None,
        description="End date for filing date range (inclusive)",
    )
    start: int = Field(
        default=0,
        ge=0,
        description="Pagination offset (0-based)",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum results to return (max 100)",
    )
    sort_field: EFTSSortField = Field(
        default=EFTSSortField.relevance,
        description="Field to sort results by",
    )
    sort_order: EFTSSortOrder = Field(
        default=EFTSSortOrder.desc,
        description="Sort order (asc or desc)",
    )

    def to_api_params(self) -> dict[str, str | int]:
        """Convert to EFTS API query parameters."""
        params: dict[str, str | int] = {
            "q": self.query,
            "from": self.start,
            "size": self.limit,
            "sort": f"{self.sort_field.value}:{self.sort_order.value}",
        }

        if self.forms:
            params["forms"] = ",".join(self.forms)

        if self.ciks:
            params["ciks"] = ",".join(self.ciks)

        if self.tickers:
            params["tickers"] = ",".join(self.tickers)

        if self.start_date:
            params["startdt"] = self.start_date.isoformat()

        if self.end_date:
            params["enddt"] = self.end_date.isoformat()

        return params


class EFTSHit(BaseModel):
    """Individual search result from EFTS API."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    accession_number: str = Field(
        description="SEC accession number (format: 0001234567-XX-XXXXXX)",
    )
    cik: str = Field(
        description="Central Index Key (10-digit padded)",
    )
    company_name: str = Field(
        description="Company name from filing",
    )
    tickers: list[str] = Field(
        default_factory=list,
        description="Ticker symbols associated with the filing when available",
    )
    form_type: str = Field(
        description="SEC form type (e.g., 10-K, 8-K)",
    )
    filed_date: date = Field(
        description="Date the filing was submitted",
    )
    file_number: str | None = Field(
        default=None,
        description="SEC file number if available",
    )
    film_number: str | None = Field(
        default=None,
        description="SEC film number if available",
    )
    snippet: str = Field(
        default="",
        description="Text snippet showing query match context",
    )
    score: float = Field(
        default=0.0,
        ge=0.0,
        description="Relevance score from search engine",
    )
    filing_url: str | None = Field(
        default=None,
        description="URL to the filing on EDGAR",
    )

    @property
    def edgar_url(self) -> str:
        """Generate EDGAR filing URL from accession number."""
        # Convert accession format: 0001234567-XX-XXXXXX -> 0001234567XXXXXXXX
        clean_accession = self.accession_number.replace("-", "")
        return (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{self.cik.lstrip('0')}/{clean_accession}/"
        )

    @property
    def ticker(self) -> str | None:
        """Return the first ticker symbol if available."""
        if not self.tickers:
            return None
        for ticker in self.tickers:
            cleaned = ticker.strip()
            if cleaned:
                return cleaned
        return None


class EFTSSearchResponse(BaseModel):
    """Paginated response from EFTS search API."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    query: str = Field(
        description="The search query that was executed",
    )
    total: int = Field(
        ge=0,
        description="Total number of matching results",
    )
    hits: list[EFTSHit] = Field(
        default_factory=list,
        description="List of search result hits",
    )
    start: int = Field(
        default=0,
        ge=0,
        description="Pagination offset used",
    )
    limit: int = Field(
        default=10,
        ge=1,
        description="Page size used",
    )

    @property
    def has_more(self) -> bool:
        """Check if there are more results to fetch."""
        return self.start + len(self.hits) < self.total

    @property
    def next_offset(self) -> int:
        """Get the offset for the next page of results."""
        return self.start + len(self.hits)


class EFTSBatchResult(BaseModel):
    """Result from a single query in a batch search."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    query: str = Field(
        description="The search query that was executed",
    )
    hits: list[EFTSHit] = Field(
        default_factory=list,
        description="List of search result hits",
    )
    total: int = Field(
        default=0,
        ge=0,
        description="Total number of matching results",
    )
    error: str | None = Field(
        default=None,
        description="Error message if this query failed",
    )

    @property
    def success(self) -> bool:
        """Check if this query succeeded."""
        return self.error is None


class EFTSError(BaseModel):
    """Error response from EFTS API."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    status: int = Field(
        description="HTTP status code",
    )
    message: str = Field(
        description="Error message",
    )
    detail: str | None = Field(
        default=None,
        description="Additional error details",
    )
