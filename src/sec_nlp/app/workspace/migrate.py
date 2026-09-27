# src/sec_nlp/app/workspace/migrate.py
"""Import legacy investing evidence without altering the original workspace.

All source records are validated before the first import. Stable note and brief
identifiers make reruns additive and idempotent. Recognized cached submissions
become offline evidence; ambiguous cache trees remain explicit external pointers.
"""

import hashlib
from pathlib import Path

from sec_nlp.app.pulse.storage import (
    _write_new,
    load_brief,
    load_journal,
    load_settings,
)
from sec_nlp.app.workspace.legacy_cache import import_legacy_caches
from sec_nlp.app.workspace.models import CachePointer, MigrationResult
from sec_nlp.app.workspace.store import WorkspaceStore


def _prepare_recipes(
    source: Path, destination: Path
) -> tuple[tuple[Path, str], ...]:
    """Validate authored jobs and catalogs before assigning immutable destinations."""
    candidates = tuple(
        path
        for path in sorted((source / "jobs").rglob("*"))
        if path.is_file() and path.suffix.lower() in {".yaml", ".yml", ".json"}
    )
    if not candidates:
        return ()
    import yaml
    from pydantic import TypeAdapter

    from sec_nlp.app.workspace.recipes import (
        RecipeCatalog,
        ResearchRecipe,
        _merge_settings,
        load_recipe,
    )
    from sec_nlp.types import JsonDict

    prepared: dict[Path, str] = {}
    origin_key = hashlib.sha256(str(source).encode()).hexdigest()[:16]
    for path in candidates:
        parsed = TypeAdapter(JsonDict).validate_python(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )
        recipes: list[ResearchRecipe] = []
        if "recipes" in parsed:
            catalog = RecipeCatalog.model_validate(parsed)
            for recipe in catalog.recipes.values():
                stages = [
                    step.model_copy(
                        update={
                            "overrides": _merge_settings(
                                catalog.profiles.get(step.pipeline, {}),
                                step.overrides,
                            )
                        }
                    )
                    for step in recipe.stages
                ]
                recipes.append(
                    ResearchRecipe.model_validate(
                        recipe.model_copy(
                            update={"stages": stages}
                        ).model_dump()
                    )
                )
        else:
            recipes.append(load_recipe(path))
        for recipe in recipes:
            content = recipe.model_dump_json(indent=2) + "\n"
            identity = hashlib.sha256(content.encode()).hexdigest()
            target = destination / "recipes" / origin_key / f"{identity}.json"
            if (
                target.exists()
                and target.read_text(encoding="utf-8") != content
            ):
                raise ValueError(f"Conflicting imported recipe at {target}")
            prepared[target] = content
    return tuple(prepared.items())


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
    recipes = _prepare_recipes(source, store.path)
    existing_notes = {entry.entry_id: entry for entry in store.list_notes()}
    existing_briefs = {
        brief.brief_id: brief for brief in store.list_briefs(limit=None)
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
    caches = tuple(
        source / name
        for name in ("cache", ".cache", "downloads", "sec-edgar-filings")
        if (source / name).is_dir()
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
    )
    filings_imported, documents_imported, warnings = import_legacy_caches(
        caches, store
    )
    recipes_imported = 0
    for path, content in recipes:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_new(path, content)
            recipes_imported += 1
    return MigrationResult(
        source=source,
        settings_imported=settings_imported,
        notes_imported=notes_imported,
        briefs_imported=briefs_imported,
        cache_pointers_imported=pointers_imported,
        recipes_imported=recipes_imported,
        recipe_paths=tuple(path for path, _ in recipes),
        filings_imported=filings_imported,
        documents_imported=documents_imported,
        warnings=warnings,
    )
