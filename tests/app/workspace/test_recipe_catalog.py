# tests/app/workspace/test_recipe_catalog.py
"""Tests for exact authored-job preservation and repeatable catalog migration."""

import hashlib
import json
from pathlib import Path

from scripts.migrate.research_recipes import migrate_recipe_catalog
from sec_nlp.app.workspace.recipes import load_recipe


def test_all_authored_settings_match_original_fingerprints() -> None:
    """Verify every migrated job against its pre-consolidation expanded settings."""
    root = Path(__file__).resolve().parents[3]
    fingerprints = json.loads(
        (root / "tests/fixtures/recipe_hashes.json").read_text()
    )
    assert len(fingerprints) == 80
    for relative, expected in fingerprints.items():
        recipe = load_recipe(root / "jobs" / relative)
        payload = json.loads(recipe.model_dump_json())
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        assert hashlib.sha256(canonical.encode()).hexdigest() == expected, (
            relative
        )


def test_catalog_migration_is_repeatable(tmp_path: Path) -> None:
    """Expand compact profiles identically across repeated migration runs."""
    for label, limit in (("first", 5), ("second", 10)):
        (tmp_path / f"{label}.yaml").write_text(
            f"name: {label}\ndefaults:\n  email: test@example.com\nstages:\n"
            f"  - id: evidence\n    pipeline: retrieve\n    overrides:\n"
            f"      limit: {limit}\n      queries: [supply]\n      symbols: [AAPL]\n"
        )
    originals = {
        path.name: load_recipe(path) for path in tmp_path.glob("*.yaml")
    }
    first = migrate_recipe_catalog(tmp_path)
    second = migrate_recipe_catalog(tmp_path)
    assert first == second
    assert {name: load_recipe(tmp_path / name) for name in first} == originals
