# src/sec_nlp/pipelines/runtime/state.py
"""Incremental processing state models and persistence helpers for runtimes.

This module consolidates the previous state model and store split into one
runtime-owned implementation. Presets use it to track processed accessions
without routing through a separate package hierarchy.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.infra.logger import logger
from sec_nlp.types import JsonDict

type ProcessingStatus = Literal["success", "partial", "skipped"]

STATE_DIR_NAME = ".sec_nlp_state"
STATE_FILE_SUFFIX = "_state.json"


class ProcessedAccession(BaseModel):
    """Immutable record of one accession processed by a pipeline run.

    Attributes:
        accession_number: SEC filing accession number or equivalent identifier.
        symbol: Uppercase ticker symbol for the processed filing.
        processed_at: UTC timestamp when the accession was recorded.
        pipeline_type: Pipeline preset name that processed the accession.
        run_id: UUID for the run that produced the record.
        chunk_count: Number of chunks produced from the accession.
        status: Terminal processing status for the accession.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    accession_number: str = Field(
        description="SEC filing accession number (e.g., 0001558370-20-014436).",
    )
    symbol: str = Field(description="Ticker symbol in uppercase form.")
    processed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the accession was processed.",
    )
    pipeline_type: str = Field(
        description="Pipeline preset name that processed this accession.",
    )
    run_id: UUID = Field(
        description="UUID of the run that processed the accession."
    )
    chunk_count: int = Field(
        default=0,
        ge=0,
        description="Number of chunks produced from this accession.",
    )
    status: ProcessingStatus = Field(
        default="success",
        description="Processing status for the accession.",
    )


class ProcessingStateMetadata(BaseModel):
    """Metadata stored alongside a persisted processing-state file.

    Attributes:
        pipeline_type: Pipeline preset name that owns the state file.
        created_at: UTC timestamp when the state file was created.
        updated_at: UTC timestamp when the state file was last updated.
        version: Integer state-file format version.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    pipeline_type: str = Field(
        description="Pipeline preset name that owns the state file.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this state file was created.",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this state file was last updated.",
    )
    version: int = Field(default=1, description="State file format version.")


class ProcessingStateData(BaseModel):
    """In-memory representation of one pipeline's incremental state.

    Attributes:
        metadata: File-level metadata describing the persisted state bundle.
        accessions: Mapping of uppercase ticker symbols to processed accessions.
    """

    model_config = ConfigDict(extra="ignore")

    metadata: ProcessingStateMetadata = Field(
        description="State file metadata."
    )
    accessions: dict[str, list[ProcessedAccession]] = Field(
        default_factory=dict,
        description="Mapping of symbol to processed accessions.",
    )

    def get_processed_accession_numbers(self, symbol: str) -> set[str]:
        """Return processed accession numbers for one symbol."""
        records = self.accessions.get(symbol.upper(), [])
        return {record.accession_number for record in records}

    def add_accession(self, record: ProcessedAccession) -> None:
        """Add one processed accession record when it is not already present."""
        symbol = record.symbol.upper()
        if symbol not in self.accessions:
            self.accessions[symbol] = []
        existing = {
            accession.accession_number for accession in self.accessions[symbol]
        }
        if record.accession_number not in existing:
            self.accessions[symbol].append(record)

    def clear_symbol(self, symbol: str) -> int:
        """Clear all records for one symbol and return the number removed."""
        symbol = symbol.upper()
        if symbol in self.accessions:
            count = len(self.accessions[symbol])
            del self.accessions[symbol]
            return count
        return 0

    def clear_all(self) -> int:
        """Clear all records and return the total number removed."""
        total = sum(len(records) for records in self.accessions.values())
        self.accessions.clear()
        return total


class ProcessingState:
    """JSON-backed state store for incremental pipeline runs.

    Each pipeline persists processed-accession state under a run-local
    `.sec_nlp_state` directory. The store lazily loads the state file, supports
    incremental updates, and exposes summary helpers used by analyze.
    """

    def __init__(
        self,
        state_dir: Path,
        pipeline_type: str,
        *,
        auto_save: bool = True,
    ) -> None:
        """Build a state store backed by one pipeline-specific JSON file.

        Args:
            state_dir: Directory that stores state files.
            pipeline_type: Pipeline preset name (for example, ``analyze``).
            auto_save: Whether mutating operations should persist immediately.
        """
        self._state_dir = state_dir
        self._pipeline_type = pipeline_type
        self._auto_save = auto_save
        self._data: ProcessingStateData | None = None

    @property
    def state_file(self) -> Path:
        """Return the JSON state-file path for this pipeline."""
        return self._state_dir / f"{self._pipeline_type}{STATE_FILE_SUFFIX}"

    @property
    def data(self) -> ProcessingStateData:
        """Return the loaded state data, loading it on first access."""
        if self._data is None:
            self._data = self._load()
        return self._data

    def save(self) -> None:
        """Persist the current state bundle to disk."""
        self._state_dir.mkdir(parents=True, exist_ok=True)

        if self._data is not None:
            self._data.metadata = ProcessingStateMetadata(
                pipeline_type=self._pipeline_type,
                created_at=self._data.metadata.created_at,
                updated_at=datetime.now(UTC),
                version=self._data.metadata.version,
            )

        data_dict = self.data.model_dump(mode="json")
        content = json.dumps(data_dict, indent=2, default=str)
        self.state_file.write_text(content, encoding="utf-8")
        logger.debug("Saved processing state to %s", self.state_file)

    def is_processed(self, symbol: str, accession: str) -> bool:
        """Return whether one accession has already been processed for a symbol."""
        processed = self.data.get_processed_accession_numbers(symbol)
        return accession in processed

    def get_pending_accessions(
        self,
        symbol: str,
        all_accessions: set[str],
    ) -> set[str]:
        """Return accessions that have not yet been processed for a symbol."""
        processed = self.data.get_processed_accession_numbers(symbol)
        pending = all_accessions - processed
        if processed:
            logger.info(
                "Incremental mode: %d/%d accessions already processed for %s, %d pending",
                len(processed),
                len(all_accessions),
                symbol,
                len(pending),
            )
        return pending

    def mark_processed(
        self,
        symbol: str,
        accession: str,
        *,
        run_id: UUID,
        chunk_count: int = 0,
        status: ProcessingStatus = "success",
    ) -> None:
        """Record one accession as processed for the current pipeline."""
        record = ProcessedAccession(
            accession_number=accession,
            symbol=symbol.upper(),
            pipeline_type=self._pipeline_type,
            run_id=run_id,
            chunk_count=chunk_count,
            status=status,
        )
        self.data.add_accession(record)
        self._maybe_save()
        logger.debug(
            "Marked accession %s as processed for %s (status=%s, chunks=%d)",
            accession,
            symbol,
            status,
            chunk_count,
        )

    def mark_processed_batch(
        self,
        symbol: str,
        accessions: list[str],
        *,
        run_id: UUID,
        chunk_counts: dict[str, int] | None = None,
        status: ProcessingStatus = "success",
    ) -> None:
        """Record multiple accessions as processed for the current pipeline."""
        chunk_counts = chunk_counts or {}
        for accession in accessions:
            record = ProcessedAccession(
                accession_number=accession,
                symbol=symbol.upper(),
                pipeline_type=self._pipeline_type,
                run_id=run_id,
                chunk_count=chunk_counts.get(accession, 0),
                status=status,
            )
            self.data.add_accession(record)

        self._maybe_save()
        logger.info(
            "Marked %d accessions as processed for %s",
            len(accessions),
            symbol,
        )

    def clear(self, symbol: str | None = None) -> int:
        """Clear state for one symbol or the entire pipeline and return the count."""
        if symbol is not None:
            count = self.data.clear_symbol(symbol)
            logger.info("Cleared %d records for %s", count, symbol)
        else:
            count = self.data.clear_all()
            logger.info("Cleared all %d records", count)

        self._maybe_save()
        return count

    def get_stats(self) -> JsonDict:
        """Return a JSON-safe summary of the current state bundle."""
        total_accessions = sum(
            len(records) for records in self.data.accessions.values()
        )
        symbols = list(self.data.accessions.keys())

        return {
            "pipeline_type": self._pipeline_type,
            "total_accessions": total_accessions,
            "symbols": symbols,
            "symbol_count": len(symbols),
            "state_file": str(self.state_file),
            "created_at": self.data.metadata.created_at.isoformat(),
            "updated_at": self.data.metadata.updated_at.isoformat(),
        }

    def _load(self) -> ProcessingStateData:
        """Load state from disk or initialize a fresh state bundle."""
        if self.state_file.exists():
            try:
                content = self.state_file.read_text(encoding="utf-8")
                raw_data = json.loads(content)
                return ProcessingStateData.model_validate(raw_data)
            except (json.JSONDecodeError, OSError, ValueError) as exc:
                logger.warning(
                    "Failed to load state file %s: %s. Creating new state.",
                    self.state_file,
                    exc,
                )

        return ProcessingStateData(
            metadata=ProcessingStateMetadata(
                pipeline_type=self._pipeline_type,
            ),
            accessions={},
        )

    def _maybe_save(self) -> None:
        """Persist immediately when auto-save is enabled."""
        if self._auto_save:
            self.save()


def get_state_dir(out_path: Path) -> Path:
    """Return the state directory path for one pipeline output root."""
    return out_path / STATE_DIR_NAME


def load_state(out_path: Path, pipeline_type: str) -> ProcessingState:
    """Build a state store for one output root and pipeline preset."""
    state_dir = get_state_dir(out_path)
    return ProcessingState(state_dir=state_dir, pipeline_type=pipeline_type)
