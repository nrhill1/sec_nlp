# src/sec_nlp/pipelines/state/store.py
"""State store for tracking processed accessions in incremental mode."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from sec_nlp.core.infra.logger import logger
from sec_nlp.types import JsonDict

from .models import (
    ProcessedAccession,
    ProcessingStateData,
    ProcessingStateMetadata,
)

STATE_DIR_NAME = ".sec_nlp_state"
STATE_FILE_SUFFIX = "_state.json"


class ProcessingState:
    """Manages processing state for incremental pipeline runs.

    State is persisted as JSON files in a `.sec_nlp_state/` directory
    within the configured output path. Each pipeline type has its own
    state file.

    Example:
        state = ProcessingState(
            state_dir=Path("./outputs/.sec_nlp_state"),
            pipeline_type="analyze",
        )
        pending = state.get_pending_accessions("AAPL", {"acc1", "acc2", "acc3"})
        # ... process pending accessions ...
        state.mark_processed("AAPL", "acc1", run_id=run_id, chunk_count=10)
    """

    def __init__(
        self,
        state_dir: Path,
        pipeline_type: str,
        *,
        auto_save: bool = True,
    ) -> None:
        """Initialize the state store.

        Args:
            state_dir: Directory to store state files
            pipeline_type: Type of pipeline (e.g., "analyze", "exhibit")
            auto_save: Whether to automatically save after modifications
        """
        self._state_dir = state_dir
        self._pipeline_type = pipeline_type
        self._auto_save = auto_save
        self._data: ProcessingStateData | None = None

    @property
    def state_file(self) -> Path:
        """Path to the state file for this pipeline."""
        return self._state_dir / f"{self._pipeline_type}{STATE_FILE_SUFFIX}"

    @property
    def data(self) -> ProcessingStateData:
        """Get the state data, loading from disk if needed."""
        if self._data is None:
            self._data = self._load()
        return self._data

    def _load(self) -> ProcessingStateData:
        """Load state from disk, creating new if not exists."""
        if self.state_file.exists():
            try:
                content = self.state_file.read_text(encoding="utf-8")
                raw_data = json.loads(content)
                return ProcessingStateData.model_validate(raw_data)
            except (json.JSONDecodeError, OSError, ValueError) as e:
                logger.warning(
                    "Failed to load state file %s: %s. Creating new state.",
                    self.state_file,
                    e,
                )

        # Create new state
        return ProcessingStateData(
            metadata=ProcessingStateMetadata(
                pipeline_type=self._pipeline_type,
            ),
            accessions={},
        )

    def save(self) -> None:
        """Persist current state to disk."""
        self._state_dir.mkdir(parents=True, exist_ok=True)

        # Update the updated_at timestamp
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

    def _maybe_save(self) -> None:
        """Save if auto_save is enabled."""
        if self._auto_save:
            self.save()

    def is_processed(self, symbol: str, accession: str) -> bool:
        """Check if an accession has been processed for a symbol.

        Args:
            symbol: Ticker symbol
            accession: Accession number

        Returns:
            True if the accession has been processed
        """
        processed = self.data.get_processed_accession_numbers(symbol)
        return accession in processed

    def get_pending_accessions(
        self,
        symbol: str,
        all_accessions: set[str],
    ) -> set[str]:
        """Get accessions that haven't been processed yet.

        Args:
            symbol: Ticker symbol
            all_accessions: Set of all available accession numbers

        Returns:
            Set of accession numbers that need processing
        """
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
        status: Literal["success", "partial", "skipped"] = "success",
    ) -> None:
        """Mark an accession as processed.

        Args:
            symbol: Ticker symbol
            accession: Accession number
            run_id: UUID of the current run
            chunk_count: Number of chunks produced
            status: Processing status
        """
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
        status: Literal["success", "partial", "skipped"] = "success",
    ) -> None:
        """Mark multiple accessions as processed.

        Args:
            symbol: Ticker symbol
            accessions: List of accession numbers
            run_id: UUID of the current run
            chunk_counts: Optional mapping of accession to chunk count
            status: Processing status for all accessions
        """
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
        """Clear processing state.

        Args:
            symbol: If provided, clear only for this symbol.
                    If None, clear all state.

        Returns:
            Number of records cleared
        """
        if symbol is not None:
            count = self.data.clear_symbol(symbol)
            logger.info("Cleared %d records for %s", count, symbol)
        else:
            count = self.data.clear_all()
            logger.info("Cleared all %d records", count)

        self._maybe_save()
        return count

    def get_stats(self) -> JsonDict:
        """Get statistics about the current state.

        Returns:
            Dictionary with state statistics
        """
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


def get_state_dir(out_path: Path) -> Path:
    """Get the state directory path for an output path.

    Args:
        out_path: Pipeline output path

    Returns:
        Path to the state directory
    """
    return out_path / STATE_DIR_NAME


def load_state(out_path: Path, pipeline_type: str) -> ProcessingState:
    """Convenience function to load state for a pipeline.

    Args:
        out_path: Pipeline output path
        pipeline_type: Type of pipeline

    Returns:
        ProcessingState instance
    """
    state_dir = get_state_dir(out_path)
    return ProcessingState(state_dir=state_dir, pipeline_type=pipeline_type)
