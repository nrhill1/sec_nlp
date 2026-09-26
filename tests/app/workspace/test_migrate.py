# tests/app/workspace/test_migrate.py
"""Tests for additive legacy investing migration and original-file preservation."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from sec_nlp.app.investing.models import Brief, JournalEntry
from sec_nlp.app.investing.storage import (
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
