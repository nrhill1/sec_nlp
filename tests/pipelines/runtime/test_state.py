# tests/pipelines/runtime/test_state.py
"""Tests for runtime state models and persistence helpers."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from sec_nlp.pipelines.runtime import (
    ProcessedAccession,
    ProcessingState,
    ProcessingStateData,
    ProcessingStateMetadata,
    get_state_dir,
    load_state,
)


class TestProcessedAccession:
    """Tests for ProcessedAccession model."""

    def test_create_accession_record(self) -> None:
        """Test creating a processed accession record."""
        run_id = uuid4()
        record = ProcessedAccession(
            accession_number="0001558370-20-014436",
            symbol="AAPL",
            pipeline_type="analyze",
            run_id=run_id,
            chunk_count=10,
        )

        assert record.accession_number == "0001558370-20-014436"
        assert record.symbol == "AAPL"
        assert record.pipeline_type == "analyze"
        assert record.run_id == run_id
        assert record.chunk_count == 10
        assert record.status == "success"  # default

    def test_accession_record_frozen(self) -> None:
        """Test that accession records are immutable."""
        run_id = uuid4()
        record = ProcessedAccession(
            accession_number="0001558370-20-014436",
            symbol="AAPL",
            pipeline_type="analyze",
            run_id=run_id,
        )

        with pytest.raises(ValidationError):
            record.accession_number = "different"


class TestProcessingStateData:
    """Tests for ProcessingStateData model."""

    def test_get_processed_accession_numbers(self) -> None:
        """Test retrieving processed accession numbers for a symbol."""
        run_id = uuid4()
        state = ProcessingStateData(
            metadata=ProcessingStateMetadata(pipeline_type="analyze"),
            accessions={
                "AAPL": [
                    ProcessedAccession(
                        accession_number="acc1",
                        symbol="AAPL",
                        pipeline_type="analyze",
                        run_id=run_id,
                    ),
                    ProcessedAccession(
                        accession_number="acc2",
                        symbol="AAPL",
                        pipeline_type="analyze",
                        run_id=run_id,
                    ),
                ],
            },
        )

        processed = state.get_processed_accession_numbers("AAPL")
        assert processed == {"acc1", "acc2"}

        # Case insensitive
        processed_lower = state.get_processed_accession_numbers("aapl")
        assert processed_lower == {"acc1", "acc2"}

        # Unknown symbol returns empty set
        unknown = state.get_processed_accession_numbers("MSFT")
        assert unknown == set()

    def test_add_accession(self) -> None:
        """Test adding accession records."""
        run_id = uuid4()
        state = ProcessingStateData(
            metadata=ProcessingStateMetadata(pipeline_type="analyze"),
        )

        record = ProcessedAccession(
            accession_number="acc1",
            symbol="AAPL",
            pipeline_type="analyze",
            run_id=run_id,
        )
        state.add_accession(record)

        assert "AAPL" in state.accessions
        assert len(state.accessions["AAPL"]) == 1
        assert state.accessions["AAPL"][0].accession_number == "acc1"

    def test_add_accession_no_duplicates(self) -> None:
        """Test that duplicate accessions are not added."""
        run_id = uuid4()
        state = ProcessingStateData(
            metadata=ProcessingStateMetadata(pipeline_type="analyze"),
        )

        record1 = ProcessedAccession(
            accession_number="acc1",
            symbol="AAPL",
            pipeline_type="analyze",
            run_id=run_id,
        )
        state.add_accession(record1)
        state.add_accession(record1)  # Duplicate

        assert len(state.accessions["AAPL"]) == 1

    def test_clear_symbol(self) -> None:
        """Test clearing records for a single symbol."""
        run_id = uuid4()
        state = ProcessingStateData(
            metadata=ProcessingStateMetadata(pipeline_type="analyze"),
            accessions={
                "AAPL": [
                    ProcessedAccession(
                        accession_number="acc1",
                        symbol="AAPL",
                        pipeline_type="analyze",
                        run_id=run_id,
                    ),
                ],
                "MSFT": [
                    ProcessedAccession(
                        accession_number="acc2",
                        symbol="MSFT",
                        pipeline_type="analyze",
                        run_id=run_id,
                    ),
                ],
            },
        )

        cleared = state.clear_symbol("AAPL")
        assert cleared == 1
        assert "AAPL" not in state.accessions
        assert "MSFT" in state.accessions

    def test_clear_all(self) -> None:
        """Test clearing all records."""
        run_id = uuid4()
        state = ProcessingStateData(
            metadata=ProcessingStateMetadata(pipeline_type="analyze"),
            accessions={
                "AAPL": [
                    ProcessedAccession(
                        accession_number="acc1",
                        symbol="AAPL",
                        pipeline_type="analyze",
                        run_id=run_id,
                    ),
                ],
                "MSFT": [
                    ProcessedAccession(
                        accession_number="acc2",
                        symbol="MSFT",
                        pipeline_type="analyze",
                        run_id=run_id,
                    ),
                ],
            },
        )

        cleared = state.clear_all()
        assert cleared == 2
        assert state.accessions == {}


class TestProcessingState:
    """Tests for ProcessingState store."""

    def test_create_new_state(self, tmp_path: Path) -> None:
        """Test creating a new state store."""
        state = ProcessingState(
            state_dir=tmp_path,
            pipeline_type="analyze",
        )

        assert state.state_file == tmp_path / "analyze_state.json"
        assert state.data.metadata.pipeline_type == "analyze"

    def test_is_processed(self, tmp_path: Path) -> None:
        """Test checking if an accession is processed."""
        run_id = uuid4()
        state = ProcessingState(
            state_dir=tmp_path,
            pipeline_type="analyze",
            auto_save=False,
        )

        # Initially not processed
        assert not state.is_processed("AAPL", "acc1")

        # Mark as processed
        state.mark_processed("AAPL", "acc1", run_id=run_id)

        # Now processed
        assert state.is_processed("AAPL", "acc1")
        assert not state.is_processed("AAPL", "acc2")
        assert not state.is_processed("MSFT", "acc1")

    def test_get_pending_accessions(self, tmp_path: Path) -> None:
        """Test getting pending accessions."""
        run_id = uuid4()
        state = ProcessingState(
            state_dir=tmp_path,
            pipeline_type="analyze",
            auto_save=False,
        )

        # Mark some as processed
        state.mark_processed("AAPL", "acc1", run_id=run_id)
        state.mark_processed("AAPL", "acc2", run_id=run_id)

        # Get pending
        all_accessions = {"acc1", "acc2", "acc3", "acc4"}
        pending = state.get_pending_accessions("AAPL", all_accessions)

        assert pending == {"acc3", "acc4"}

    def test_mark_processed_batch(self, tmp_path: Path) -> None:
        """Test marking multiple accessions as processed."""
        run_id = uuid4()
        state = ProcessingState(
            state_dir=tmp_path,
            pipeline_type="analyze",
            auto_save=False,
        )

        state.mark_processed_batch(
            symbol="AAPL",
            accessions=["acc1", "acc2", "acc3"],
            run_id=run_id,
            chunk_counts={"acc1": 10, "acc2": 20, "acc3": 15},
        )

        assert state.is_processed("AAPL", "acc1")
        assert state.is_processed("AAPL", "acc2")
        assert state.is_processed("AAPL", "acc3")

        # Check chunk counts are stored
        records = state.data.accessions["AAPL"]
        chunk_counts = {r.accession_number: r.chunk_count for r in records}
        assert chunk_counts == {"acc1": 10, "acc2": 20, "acc3": 15}

    def test_save_and_load(self, tmp_path: Path) -> None:
        """Test persisting and loading state."""
        run_id = uuid4()

        # Create and save state
        state1 = ProcessingState(
            state_dir=tmp_path,
            pipeline_type="analyze",
            auto_save=False,
        )
        state1.mark_processed("AAPL", "acc1", run_id=run_id, chunk_count=10)
        state1.mark_processed("AAPL", "acc2", run_id=run_id, chunk_count=20)
        state1.save()

        # Load in new instance
        state2 = ProcessingState(
            state_dir=tmp_path,
            pipeline_type="analyze",
            auto_save=False,
        )

        assert state2.is_processed("AAPL", "acc1")
        assert state2.is_processed("AAPL", "acc2")
        assert not state2.is_processed("AAPL", "acc3")

    def test_auto_save(self, tmp_path: Path) -> None:
        """Test auto-save functionality."""
        run_id = uuid4()
        state = ProcessingState(
            state_dir=tmp_path,
            pipeline_type="analyze",
            auto_save=True,  # Enable auto-save
        )

        state.mark_processed("AAPL", "acc1", run_id=run_id)

        # File should exist after mark_processed
        assert state.state_file.exists()

        # Verify content
        content = json.loads(state.state_file.read_text())
        assert "accessions" in content
        assert "AAPL" in content["accessions"]

    def test_clear_symbol(self, tmp_path: Path) -> None:
        """Test clearing state for a specific symbol."""
        run_id = uuid4()
        state = ProcessingState(
            state_dir=tmp_path,
            pipeline_type="analyze",
            auto_save=False,
        )

        state.mark_processed("AAPL", "acc1", run_id=run_id)
        state.mark_processed("MSFT", "acc2", run_id=run_id)

        cleared = state.clear("AAPL")
        assert cleared == 1

        assert not state.is_processed("AAPL", "acc1")
        assert state.is_processed("MSFT", "acc2")

    def test_clear_all(self, tmp_path: Path) -> None:
        """Test clearing all state."""
        run_id = uuid4()
        state = ProcessingState(
            state_dir=tmp_path,
            pipeline_type="analyze",
            auto_save=False,
        )

        state.mark_processed("AAPL", "acc1", run_id=run_id)
        state.mark_processed("MSFT", "acc2", run_id=run_id)

        cleared = state.clear()
        assert cleared == 2

        assert not state.is_processed("AAPL", "acc1")
        assert not state.is_processed("MSFT", "acc2")

    def test_get_stats(self, tmp_path: Path) -> None:
        """Test getting state statistics."""
        run_id = uuid4()
        state = ProcessingState(
            state_dir=tmp_path,
            pipeline_type="analyze",
            auto_save=False,
        )

        state.mark_processed("AAPL", "acc1", run_id=run_id)
        state.mark_processed("AAPL", "acc2", run_id=run_id)
        state.mark_processed("MSFT", "acc3", run_id=run_id)

        stats = state.get_stats()

        assert stats["pipeline_type"] == "analyze"
        assert stats["total_accessions"] == 3
        symbols = stats["symbols"]
        assert isinstance(symbols, list)
        assert set(symbols) == {"AAPL", "MSFT"}
        assert stats["symbol_count"] == 2

    def test_corrupted_state_file(self, tmp_path: Path) -> None:
        """Test handling of corrupted state file."""
        state_file = tmp_path / "analyze_state.json"
        state_file.write_text("invalid json {{{")

        state = ProcessingState(
            state_dir=tmp_path,
            pipeline_type="analyze",
            auto_save=False,
        )

        # Should create fresh state instead of failing
        assert state.data.metadata.pipeline_type == "analyze"
        assert state.data.accessions == {}


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_state_dir(self, tmp_path: Path) -> None:
        """Test get_state_dir function."""
        state_dir = get_state_dir(tmp_path)
        assert state_dir == tmp_path / ".sec_nlp_state"

    def test_load_state(self, tmp_path: Path) -> None:
        """Test load_state convenience function."""
        state = load_state(tmp_path, "analyze")

        assert (
            state.state_file
            == tmp_path / ".sec_nlp_state" / "analyze_state.json"
        )
        assert state.data.metadata.pipeline_type == "analyze"
