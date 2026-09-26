# tests/app/workspace/test_store.py
"""Tests for durable accession state, atomic coverage, and offline evidence."""

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import HttpUrl

from sec_nlp.app.investing.models import Brief, Headline, JournalEntry
from sec_nlp.app.workspace.models import JobRecord, ScanSpec, SourceCheckpoint
from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.core.edgar.filing_models import (
    DocumentContent,
    FilingDocument,
    FilingEntity,
    FilingManifest,
    FilingRecord,
)


def filing(*, cik: str = "123", role: str = "issuer") -> FilingRecord:
    """Build filing evidence with an explicit entity role and accession."""
    return FilingRecord(
        accession_number="0000000123-26-000001",
        entities=(FilingEntity(cik=cik, name="Example Issuer", role=role),),
        form_type="4",
        filed_date=date(2026, 9, 25),
        filing_url=HttpUrl(
            "https://www.sec.gov/Archives/edgar/data/123/000000012326000001/0000000123-26-000001-index.html"
        ),
        submission_url=HttpUrl(
            "https://www.sec.gov/Archives/edgar/data/123/000000012326000001/0000000123-26-000001.txt"
        ),
    )


def test_refresh_preserves_roles_read_and_bookmark_across_restarts(
    tmp_path: Path,
) -> None:
    """Merge duplicate accessions without losing associated entities or user state."""
    store = WorkspaceStore(tmp_path)
    first_seen = datetime(2026, 9, 25, tzinfo=UTC)
    assert (
        store.upsert_filings((filing(),), source="atom", observed_at=first_seen)
        == 1
    )
    store.set_read(filing().accession_number)
    store.set_bookmarked(filing().accession_number)
    assert (
        store.upsert_filings(
            (filing(cik="456", role="reporting owner"),), source="index"
        )
        == 0
    )
    store = WorkspaceStore(tmp_path)
    item = store.list_filings(cik="456")[0]
    assert {entity.cik for entity in item.filing.entities} == {
        "0000000123",
        "0000000456",
    }
    assert item.is_read and item.bookmarked
    assert item.first_seen_at == first_seen
    assert not store.list_filings(unread_only=True)
    assert len(store.list_filings(bookmarked_only=True)) == 1
    store.set_read(item.filing.accession_number, False)
    assert len(store.list_filings(unread_only=True)) == 1


def test_filter_literal_text_and_unknown_state_target(tmp_path: Path) -> None:
    """Treat search text literally and reject state changes for absent filings."""
    store = WorkspaceStore(tmp_path)
    store.upsert_filings((filing(),))
    assert len(store.list_filings(query="example", forms=("4",))) == 1
    assert not store.list_filings(query="%")
    assert not store.list_filings(forms=("10-K",))
    with pytest.raises(ValueError, match="not in this workspace"):
        store.set_read("missing")


def test_index_checkpoint_and_filings_roll_back_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Never advance coverage or retain half an index if checkpoint saving fails."""
    store = WorkspaceStore(tmp_path)
    checkpoint = SourceCheckpoint(
        source="sec-index", scope="index-url", status="complete"
    )

    def fail_checkpoint(
        connection: sqlite3.Connection, value: SourceCheckpoint
    ) -> None:
        """Simulate a write failure after filing inserts within the transaction."""
        raise sqlite3.OperationalError("disk write failure")

    monkeypatch.setattr(store, "_save_checkpoint", fail_checkpoint)
    with pytest.raises(sqlite3.OperationalError):
        store.ingest_filings((filing(),), checkpoint)
    assert store.list_filings() == ()
    assert store.list_checkpoints() == ()


def test_failed_refresh_keeps_successful_coverage_evidence(
    tmp_path: Path,
) -> None:
    """Expose the latest failure while preserving prior successful artifact metadata."""
    store = WorkspaceStore(tmp_path)
    completed = datetime(2026, 9, 25, tzinfo=UTC)
    store.ingest_filings(
        (filing(),),
        SourceCheckpoint(
            source="sec-index",
            scope="daily",
            status="complete",
            checked_at=completed,
            processed_at=completed,
            content_hash="digest",
            artifact_url="https://www.sec.gov/index",
        ),
    )
    store.save_checkpoint(
        SourceCheckpoint(
            source="sec-index", scope="daily", status="error", detail="HTTP 503"
        )
    )
    checkpoint = store.list_checkpoints()[0]
    assert checkpoint.status == "error"
    assert checkpoint.last_success_at == completed
    assert checkpoint.processed_at == completed
    assert checkpoint.content_hash == "digest"
    assert len(store.list_filings()) == 1


def test_manifest_and_document_cache_do_not_mark_read(tmp_path: Path) -> None:
    """Store full content atomically and reuse it offline without implicit review state."""
    store = WorkspaceStore(tmp_path)
    store.upsert_filings((filing(),))
    document = FilingDocument(
        filename="../../source.htm",
        url=HttpUrl("https://www.sec.gov/Archives/source.htm"),
    )
    manifest = FilingManifest(filing=filing(), documents=(document,))
    store.save_manifest(manifest)
    content = DocumentContent(
        document=document, text="Full body\n" * 1000, html="<p>Full body</p>"
    )
    path = store.cache_document(content)
    assert path.parent == tmp_path / "documents"
    assert WorkspaceStore(tmp_path).load_document(document) == content
    assert store.get_manifest(filing().accession_number) == manifest
    assert not store.list_filings()[0].is_read
    path.unlink()
    assert store.load_document(document) is None


def test_reconciliation_preserves_withdrawn_evidence_and_user_state(
    tmp_path: Path,
) -> None:
    """Flag corrected-index removals while retaining notes and reversible user choices."""
    store = WorkspaceStore(tmp_path)
    checkpoint = SourceCheckpoint(
        source="sec-index",
        scope="quarter",
        artifact_url="https://www.sec.gov/Archives/edgar/full-index/2026/QTR3/master.idx",
        status="complete",
    )
    store.ingest_filings((filing(),), checkpoint)
    store.set_bookmarked(filing().accession_number)
    store.set_read(filing().accession_number)
    entry = JournalEntry(
        entry_id="c" * 32,
        created_at=datetime(2026, 9, 25, tzinfo=UTC),
        observation="Preserve this note",
    )
    store.save_note(entry, related_accession=filing().accession_number)
    store.reconcile_index((), checkpoint)
    item = WorkspaceStore(tmp_path).list_filings()[0]
    assert item.source_withdrawn and item.is_read and item.bookmarked
    assert store.list_notes(accession_number=filing().accession_number) == (
        entry,
    )
    store.reconcile_index((filing(),), checkpoint)
    assert not store.list_filings()[0].source_withdrawn
    with pytest.raises(ValueError, match="complete artifact"):
        store.reconcile_index(
            (), checkpoint.model_copy(update={"status": "partial"})
        )


def test_first_full_index_reconciles_existing_daily_memberships(
    tmp_path: Path,
) -> None:
    """Detect daily-only removals during the first authoritative quarterly refresh."""
    store = WorkspaceStore(tmp_path)
    store.ingest_filings(
        (filing(),),
        SourceCheckpoint(
            source="sec-index",
            scope="daily",
            artifact_url="https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/master.20260925.idx",
            status="complete",
        ),
    )
    other = filing().model_copy(
        update={"accession_number": "0000000123-26-000002"}
    )
    store.ingest_filings(
        (other,),
        SourceCheckpoint(
            source="sec-index",
            scope="other",
            artifact_url="https://www.sec.gov/Archives/edgar/daily-index/2026/QTR2/master.20260625.idx",
            status="complete",
        ),
    )
    checkpoint = SourceCheckpoint(
        source="sec-index",
        scope="quarter",
        artifact_url="https://www.sec.gov/Archives/edgar/full-index/2026/QTR3/master.idx",
        status="complete",
    )
    store.reconcile_index((), checkpoint)
    states = {
        item.filing.accession_number: item.source_withdrawn
        for item in store.list_filings()
    }
    assert states[filing().accession_number]
    assert not states[other.accession_number]
    store.reconcile_index((filing(),), checkpoint)
    assert all(not item.source_withdrawn for item in store.list_filings())


def test_saved_scans_jobs_and_notes_retain_identity(tmp_path: Path) -> None:
    """Keep editable scans and immutable linked research across reopening."""
    store = WorkspaceStore(tmp_path)
    scan = ScanSpec(name="Ownership", forms=("4",), limit=50, max_documents=0)
    store.save_scan(scan)
    job = JobRecord(kind="scan", status="complete", scan_id=scan.scan_id)
    store.save_job(job)
    entry = JournalEntry(
        entry_id="a" * 32,
        created_at=datetime(2026, 9, 25, tzinfo=UTC),
        observation="Review ownership",
    )
    assert store.save_note(entry, related_accession=filing().accession_number)
    assert not store.save_note(entry)
    assert store.list_notes(accession_number=filing().accession_number) == (
        entry,
    )
    with pytest.raises(ValueError, match="Conflicting"):
        store.save_note(entry.model_copy(update={"observation": "Overwrite"}))
    assert WorkspaceStore(tmp_path).list_scans() == (scan,)
    assert store.list_jobs() == (job,)
    store.delete_scan(scan.scan_id)
    assert store.list_scans() == ()
    assert store.list_jobs() == (job,)


def test_news_identity_uses_ledger_and_retains_repeated_releases(
    tmp_path: Path,
) -> None:
    """Do not mark known headlines new after gaps or merge different release dates."""
    store = WorkspaceStore(tmp_path)
    headline = Headline(
        title="Policy statement",
        source="Fed",
        url=HttpUrl("https://example.com/policy"),
        published_at=datetime(2026, 9, 25, tzinfo=UTC),
        is_new=False,
    )
    store.save_news((headline,))
    assert store.list_news()[0].is_new
    store.save_news(())
    store.save_news((headline.model_copy(update={"is_new": True}),))
    assert not store.list_news()[0].is_new
    store.save_news(
        (
            headline.model_copy(
                update={"published_at": datetime(2026, 9, 26, tzinfo=UTC)}
            ),
        )
    )
    assert len(store.list_news()) == 2
    assert store.list_news()[0].is_new


def test_brief_snapshot_is_immutable_and_default_profile_offline(
    tmp_path: Path,
) -> None:
    """Create a starter without jobs and retain complete brief snapshots."""
    store = WorkspaceStore(tmp_path)
    assert store.load_settings().feeds
    assert store.list_jobs() == ()
    brief = Brief(
        brief_id="b" * 32,
        generated_at=datetime(2026, 9, 25, tzinfo=UTC),
        settings=store.load_settings(),
    )
    assert store.save_brief(brief)
    assert not store.save_brief(brief)
    assert store.list_briefs() == (brief,)
    with pytest.raises(ValueError, match="Conflicting"):
        store.save_brief(brief.model_copy(update={"demo": True}))
