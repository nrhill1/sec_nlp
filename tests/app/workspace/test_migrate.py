# tests/app/workspace/test_migrate.py
"""Tests for additive legacy investing migration and original-file preservation."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sec_nlp.app.pulse.models import Brief, JournalEntry
from sec_nlp.app.pulse.storage import (
    initialize_workspace,
    save_brief,
    save_note,
    starter_settings,
)
from sec_nlp.app.workspace.migrate import migrate_workspace
from sec_nlp.app.workspace.store import WorkspaceStore


def test_migration_is_idempotent_and_preserves_original_files(
    tmp_path: Path,
) -> None:
    """Import profile, journal, reports, and cache references without moving originals."""
    origin = tmp_path / "legacy"
    settings = starter_settings(("ACME",))
    initialize_workspace(origin, settings)
    entry = JournalEntry(
        entry_id="a" * 32,
        created_at=datetime(2026, 9, 25, tzinfo=UTC),
        observation="Original wording",
    )
    save_note(origin, entry)
    brief = Brief(
        brief_id="b" * 32,
        generated_at=datetime(2026, 9, 25, tzinfo=UTC),
        settings=settings,
        journal=(entry,),
    )
    save_brief(origin, brief)
    (origin / "downloads").mkdir()
    (origin / "downloads" / "filing.txt").write_text("original filing")
    before = {
        path.relative_to(origin): path.read_bytes()
        for path in origin.rglob("*")
        if path.is_file()
    }
    store = WorkspaceStore(tmp_path / "destination")
    first = migrate_workspace(origin, store)
    assert first.settings_imported
    assert (
        first.notes_imported
        == first.briefs_imported
        == first.cache_pointers_imported
        == 1
    )
    assert store.load_settings() == settings
    assert store.list_notes() == (entry,)
    assert store.list_briefs() == (brief,)
    second = migrate_workspace(origin, store)
    assert not second.settings_imported
    assert (
        second.notes_imported
        == second.briefs_imported
        == second.cache_pointers_imported
        == 0
    )
    assert before == {
        path.relative_to(origin): path.read_bytes()
        for path in origin.rglob("*")
        if path.is_file()
    }
    assert store.list_cache_pointers()[0].external


def test_migration_preserves_edited_profile_and_rejects_corruption(
    tmp_path: Path,
) -> None:
    """Do not overwrite current preferences or partially import corrupt source records."""
    origin = tmp_path / "legacy"
    initialize_workspace(origin, starter_settings(("OLD",)))
    journal = origin / "journal"
    journal.mkdir()
    (journal / "corrupt.json").write_text("{")
    store = WorkspaceStore(tmp_path / "destination")
    edited = starter_settings(("NEW",))
    store.save_settings(edited)
    with pytest.raises(ValueError, match="corrupt.json"):
        migrate_workspace(origin, store)
    assert store.load_settings() == edited
    assert store.list_notes() == ()
    (journal / "corrupt.json").unlink()
    assert not migrate_workspace(origin, store).settings_imported
    assert store.load_settings() == edited


def test_migration_preserves_authored_job_settings_as_immutable_recipes(
    tmp_path: Path,
) -> None:
    """Retain exact stage overrides, preserve originals, and deduplicate repeated imports."""
    import json

    from sec_nlp.app.workspace.recipes import load_recipe

    origin = tmp_path / "legacy"
    initialize_workspace(origin)
    jobs = origin / "jobs"
    jobs.mkdir()
    original = jobs / "research.json"
    original.write_text(
        json.dumps(
            {
                "name": "Demand",
                "defaults": {"email": "research@example.com"},
                "stages": [
                    {
                        "id": "find",
                        "pipeline": "retrieve",
                        "overrides": {"queries": ["demand"], "max_results": 17},
                    }
                ],
            }
        )
    )
    before = original.read_text()
    store = WorkspaceStore(tmp_path / "destination")
    first = migrate_workspace(origin, store)
    assert first.recipes_imported == 1
    assert load_recipe(first.recipe_paths[0]) == load_recipe(original)
    assert original.read_text() == before
    assert migrate_workspace(origin, store).recipes_imported == 0


def test_migration_recovers_cached_sec_documents_for_offline_reading(
    tmp_path: Path,
) -> None:
    """Read a migrated submission offline using its declared CIK, not its prefix."""
    from sec_nlp.app.workspace.service import WorkspaceService

    origin = tmp_path / "legacy"
    initialize_workspace(origin)
    accession = "0000999999-26-000001"
    folder = origin / "sec-edgar-filings" / "ACME" / "10-K" / accession
    folder.mkdir(parents=True)
    original = folder / "full-submission.txt"
    original.write_text(
        "<SEC-DOCUMENT>0000999999-26-000001.txt\n"
        "<SEC-HEADER>\n"
        "ACCESSION NUMBER: 0000999999-26-000001\n"
        "CONFORMED SUBMISSION TYPE: 10-K\n"
        "FILED AS OF DATE: 20260925\n"
        "<ACCEPTANCE-DATETIME>20260925173000\n"
        "FILER:\n\tCOMPANY DATA:\n"
        "\t\tCOMPANY CONFORMED NAME: Example Issuer\n"
        "\t\tCENTRAL INDEX KEY: 0000000123\n"
        "</SEC-HEADER>\n"
        "<DOCUMENT>\n<TYPE>10-K\n<SEQUENCE>1\n<FILENAME>annual.htm\n"
        "<DESCRIPTION>Annual report\n<TEXT>"
        "<html><body><h1>Demand</h1><p>Full cached evidence.</p></body></html>"
        "</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>"
    )
    before = original.read_bytes()
    store = WorkspaceStore(tmp_path / "destination")
    imported = migrate_workspace(origin, store)
    assert imported.filings_imported == 1
    assert imported.documents_imported == 2
    assert imported.warnings == ()
    filing = store.get_filing(accession)
    assert filing is not None
    assert filing.entities[0].cik == "0000000123"
    assert "/data/123/" in str(filing.filing_url)
    assert filing.accepted_at is not None
    assert filing.accepted_at.hour == 17
    service = WorkspaceService(store)
    content = asyncio.run(service.read(accession, filename="annual.htm"))
    assert content.text == "Demand\nFull cached evidence."
    assert content.html and "<h1>Demand</h1>" in content.html
    assert original.read_bytes() == before
    repeated = migrate_workspace(origin, store)
    assert repeated.filings_imported == repeated.documents_imported == 0


def test_cache_migration_keeps_ambiguous_identity_as_visible_pointer(
    tmp_path: Path,
) -> None:
    """Never invent a CIK from the accession or a ticker-named directory."""
    origin = tmp_path / "legacy"
    initialize_workspace(origin)
    cache = origin / "downloads" / "ACME" / "0000999999-26-000001"
    cache.mkdir(parents=True)
    original = cache / "full-submission.txt"
    original.write_text(
        "<SEC-HEADER>\nACCESSION NUMBER: 0000999999-26-000001\n"
        "CONFORMED SUBMISSION TYPE: 10-K\n</SEC-HEADER>"
    )
    store = WorkspaceStore(tmp_path / "destination")
    imported = migrate_workspace(origin, store)
    assert imported.filings_imported == imported.documents_imported == 0
    assert "declared party CIK" in imported.warnings[0]
    assert store.list_cache_pointers()[0].external
    assert original.exists()
    assert store.list_filings() == ()


@pytest.mark.parametrize("binary", ["%PDF-1.7\nPDF body", "binary\x00payload"])
def test_mixed_submission_preserves_readable_evidence_and_binary_sources(
    tmp_path: Path, binary: str
) -> None:
    """Retain the filing and all source links when one attachment is unsupported."""
    origin = tmp_path / "legacy"
    initialize_workspace(origin)
    cache = origin / "sec-edgar-filings"
    cache.mkdir()
    original = cache / "full-submission.txt"
    original.write_text(
        "<SEC-HEADER>\nACCESSION NUMBER: 0000999999-26-000001\n"
        "CONFORMED SUBMISSION TYPE: 10-K\nFILER:\n"
        "COMPANY CONFORMED NAME: Example\nCENTRAL INDEX KEY: 123\n"
        "</SEC-HEADER>\n"
        "<DOCUMENT>\n<TYPE>10-K\n<FILENAME>annual.htm\n<text>"
        "<html><body>Readable evidence<description>not metadata</description></body></html>"
        "</text></DOCUMENT>\n"
        "<DOCUMENT>\n<TYPE>EX-99\n<FILENAME>attachment.pdf\n<TEXT>"
        f"{binary}</TEXT></DOCUMENT>"
    )
    before = original.read_bytes()
    store = WorkspaceStore(tmp_path / "destination")
    imported = migrate_workspace(origin, store)
    assert imported.filings_imported == 1
    manifest = store.get_manifest("0000999999-26-000001")
    assert manifest is not None
    assert len(manifest.documents) == 3
    primary, attachment, _ = manifest.documents
    content = store.load_document(primary)
    assert content is not None and "Readable evidence" in content.text
    assert primary.description == ""
    assert attachment.filename == "attachment.pdf"
    assert store.load_document(attachment) is None
    assert any("attachment.pdf" in warning for warning in imported.warnings)
    assert original.read_bytes() == before
