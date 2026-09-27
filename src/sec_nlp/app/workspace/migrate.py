# src/sec_nlp/app/workspace/migrate.py
"""Import legacy investing evidence without altering the original workspace.

All source records are validated before the first import. Stable note and brief
identifiers make reruns additive and idempotent, while existing cache trees are
referenced instead of copied or claimed as newly downloaded evidence.
"""

from pathlib import Path

from sec_nlp.app.pulse.storage import (
    load_brief,
    load_journal,
    load_settings,
)
from sec_nlp.app.workspace.models import CachePointer, MigrationResult
from sec_nlp.app.workspace.store import WorkspaceStore


def migrate_workspace(origin: Path, store: WorkspaceStore) -> MigrationResult:
    """Import existing profile, notes, reports, and cache references safely.

    Args:
        origin: Legacy investing directory containing ``config.json``.
        store: Destination ledger, possibly in the same directory.

    Returns:
        Counts of newly imported records; originals are never modified.

    Raises:
        OSError: If a source record cannot be read.
        ValueError: If source records are corrupt or reuse conflicting IDs.
    """
    source = origin.expanduser().resolve()
    settings = load_settings(source)
    notes = load_journal(source)
    briefs = tuple(
        load_brief(path)
        for path in sorted((source / "reports").glob("*/brief.json"))
    )
    existing_notes = {entry.entry_id: entry for entry in store.list_notes()}
    existing_briefs = {
        brief.brief_id: brief for brief in store.list_briefs(limit=1_000_000)
    }
    for entry in notes:
        if (
            entry.entry_id in existing_notes
            and existing_notes[entry.entry_id] != entry
        ):
            raise ValueError(f"Conflicting journal identity: {entry.entry_id}")
        existing_notes[entry.entry_id] = entry
    for brief in briefs:
        if (
            brief.brief_id in existing_briefs
            and existing_briefs[brief.brief_id] != brief
        ):
            raise ValueError(f"Conflicting brief identity: {brief.brief_id}")
        existing_briefs[brief.brief_id] = brief
    settings_imported = store.import_settings(settings)
    notes_imported = sum(store.save_note(entry) for entry in notes)
    briefs_imported = sum(store.save_brief(brief) for brief in briefs)
    caches = (
        source / name
        for name in ("cache", ".cache", "downloads", "sec-edgar-filings")
    )
    pointers_imported = sum(
        store.save_cache_pointer(
            CachePointer(
                key=f"legacy:{path}",
                path=path,
                media_type="inode/directory",
                external=True,
            )
        )
        for path in caches
        if path.is_dir()
    )
    return MigrationResult(
        source=source,
        settings_imported=settings_imported,
        notes_imported=notes_imported,
        briefs_imported=briefs_imported,
        cache_pointers_imported=pointers_imported,
    )
