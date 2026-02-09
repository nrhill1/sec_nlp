# src/sec_nlp/pipelines/state/models.py
"""Data models for pipeline processing state tracking."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProcessedAccession(BaseModel):
    """Record of a processed accession for incremental processing."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    accession_number: str = Field(
        description="SEC filing accession number (e.g., 0001558370-20-014436)",
    )
    symbol: str = Field(
        description="Ticker symbol (uppercase)",
    )
    processed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the accession was processed",
    )
    pipeline_type: str = Field(
        description="Type of pipeline that processed this accession",
    )
    run_id: UUID = Field(
        description="UUID of the run that processed this accession",
    )
    chunk_count: int = Field(
        default=0,
        ge=0,
        description="Number of chunks produced from this accession",
    )
    status: Literal["success", "partial", "skipped"] = Field(
        default="success",
        description="Processing status: success, partial (some chunks failed), or skipped",
    )


class ProcessingStateMetadata(BaseModel):
    """Metadata for the processing state file."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    pipeline_type: str = Field(
        description="Type of pipeline this state belongs to",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this state file was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this state file was last updated",
    )
    version: int = Field(
        default=1,
        description="State file format version",
    )


class ProcessingStateData(BaseModel):
    """Complete state data for a pipeline."""

    model_config = ConfigDict(
        extra="ignore",
    )

    metadata: ProcessingStateMetadata = Field(
        description="State file metadata",
    )
    accessions: dict[str, list[ProcessedAccession]] = Field(
        default_factory=dict,
        description="Mapping of symbol to list of processed accessions",
    )

    def get_processed_accession_numbers(self, symbol: str) -> set[str]:
        """Get set of processed accession numbers for a symbol."""
        records = self.accessions.get(symbol.upper(), [])
        return {r.accession_number for r in records}

    def add_accession(self, record: ProcessedAccession) -> None:
        """Add a processed accession record."""
        symbol = record.symbol.upper()
        if symbol not in self.accessions:
            self.accessions[symbol] = []
        # Avoid duplicates
        existing = {r.accession_number for r in self.accessions[symbol]}
        if record.accession_number not in existing:
            self.accessions[symbol].append(record)

    def clear_symbol(self, symbol: str) -> int:
        """Clear all records for a symbol. Returns number of records cleared."""
        symbol = symbol.upper()
        if symbol in self.accessions:
            count = len(self.accessions[symbol])
            del self.accessions[symbol]
            return count
        return 0

    def clear_all(self) -> int:
        """Clear all records. Returns total number of records cleared."""
        total = sum(len(records) for records in self.accessions.values())
        self.accessions.clear()
        return total
