# tests/app/workspace/test_headlines_export.py
"""Tests for offline headline relationships and journal provenance in exports."""

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import HttpUrl

from sec_nlp.app.pulse.models import Headline, JournalEntry
from sec_nlp.app.workspace.export import export_workspace
from sec_nlp.app.workspace.headlines import related_headlines
from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.core.edgar.filing_models import FilingEntity, FilingRecord


def test_related_headline_uses_declared_name_and_preserves_source() -> None:
    """Match the issuer's shortened legal name and expose the matching reason."""
    filing = FilingRecord(
        accession_number="0000123456-26-000001",
        form_type="10-K",
        entities=(FilingEntity(cik="320193", name="Apple Inc."),),
        filing_url=HttpUrl("https://www.sec.gov/Archives/example-index.html"),
        submission_url=HttpUrl("https://www.sec.gov/Archives/example.txt"),
    )
    headline = Headline(
        title="Apple announces capacity expansion",
        source="Example Publisher",
        url=HttpUrl("https://example.com/apple"),
    )
    matched = related_headlines(filing, (headline,), ())
    assert matched == ((headline, "Headline mentions filing entity: apple"),)
    assert matched[0][0].published_at is None


def test_export_preserves_filing_note_links(tmp_path: Path) -> None:
    """Carry all linked accessions into a JSON report without altering the journal."""
    store = WorkspaceStore(tmp_path / "workspace")
    entry = JournalEntry(
        entry_id="a" * 32,
        created_at=datetime.now(UTC),
        observation="Evidence to review",
    )
    filing = FilingRecord(
        accession_number="0000123456-26-000001",
        form_type="8-K",
        filing_url=HttpUrl("https://www.sec.gov/Archives/example-index.html"),
        submission_url=HttpUrl("https://www.sec.gov/Archives/example.txt"),
    )
    store.upsert_filings((filing,))
    store.save_note(entry, related_accession=filing.accession_number)
    destination = export_workspace(
        store, tmp_path / "report.json", output_format="json"
    )
    payload = json.loads(destination.read_text())
    assert payload["note_links"][entry.entry_id] == [filing.accession_number]
    assert store.list_notes(accession_number=filing.accession_number) == (
        entry,
    )
