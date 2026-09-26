# src/scripts/migrate/research_recipes.py
"""Consolidate authored research jobs into reusable data profiles and a catalog.

Migration expands every source recipe before comparing the new representation.
Reference files keep existing benchmark paths usable, while repeated settings
move into one human-readable catalog without changing selected parameters.
"""

import hashlib
import json
import os
from collections import Counter
from pathlib import Path

import yaml
from pydantic import TypeAdapter

from sec_nlp.app.workspace.recipes import (
    RecipeCatalog,
    ResearchRecipe,
    load_recipe,
)
from sec_nlp.core.types import as_json_dict
from sec_nlp.types import JsonDict, JsonValue


def _canonical(value: JsonValue) -> str:
    """Serialize JSON data deterministically for equality and provenance checks."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _common(payloads: list[JsonDict]) -> JsonDict:
    """Find reusable defaults without introducing keys absent from any recipe."""
    if not payloads:
        return {}
    shared_keys = set(payloads[0]).intersection(
        *(set(item) for item in payloads[1:])
    )
    result: JsonDict = {}
    for key in sorted(shared_keys):
        values = [item[key] for item in payloads]
        nested = [as_json_dict(value) for value in values]
        if all(item is not None for item in nested):
            common = _common([item for item in nested if item is not None])
            if common:
                result[key] = common
        else:
            counts = Counter(_canonical(value) for value in values)
            encoded, frequency = counts.most_common(1)[0]
            if frequency > 1:
                result[key] = next(
                    value for value in values if _canonical(value) == encoded
                )
    return result


def _difference(base: JsonDict, values: JsonDict) -> JsonDict:
    """Retain only explicit settings that differ from shared profile defaults."""
    result: JsonDict = {}
    for key, value in values.items():
        old = base.get(key)
        old_mapping, new_mapping = as_json_dict(old), as_json_dict(value)
        if old_mapping is not None and new_mapping is not None:
            delta = _difference(old_mapping, new_mapping)
            if delta:
                result[key] = delta
        elif key not in base or _canonical(old) != _canonical(value):
            result[key] = value
    return result


def migrate_recipe_catalog(directory: Path) -> dict[str, str]:
    """Migrate job files and verify exact expanded settings against their originals.

    Args:
        directory: Directory containing authored JSON/YAML research jobs.

    Returns:
        SHA-256 hashes of expanded recipes keyed by repository job-relative path.

    Raises:
        ValueError: If a migrated recipe differs from its original settings.
    """
    directory = directory.resolve()
    originals: dict[str, ResearchRecipe] = {}
    for path in sorted(directory.rglob("*.yaml")):
        if path.name == "catalog.yaml":
            continue
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict) or not (
            "stages" in parsed or "catalog" in parsed
        ):
            continue
        originals[str(path.relative_to(directory))] = load_recipe(path)
    by_pipeline: dict[str, list[JsonDict]] = {}
    for recipe in originals.values():
        for step in recipe.stages:
            by_pipeline.setdefault(step.pipeline, []).append(step.overrides)
    profiles = {
        name: _common(payloads) for name, payloads in by_pipeline.items()
    }
    compact = {
        name: recipe.model_copy(
            update={
                "stages": [
                    step.model_copy(
                        update={
                            "overrides": _difference(
                                profiles[step.pipeline], step.overrides
                            )
                        }
                    )
                    for step in recipe.stages
                ]
            }
        )
        for name, recipe in originals.items()
    }
    catalog = RecipeCatalog(profiles=profiles, recipes=compact)
    payload = TypeAdapter(JsonDict).validate_json(catalog.model_dump_json())
    catalog_path = directory / "catalog.yaml"
    catalog_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, width=100), encoding="utf-8"
    )
    hashes: dict[str, str] = {}
    for name, original in originals.items():
        path = directory / name
        reference = {
            "schema_version": 1,
            "catalog": os.path.relpath(catalog_path, path.parent),
            "recipe": name,
        }
        path.write_text(
            yaml.safe_dump(reference, sort_keys=False), encoding="utf-8"
        )
        expanded = load_recipe(path)
        if expanded != original:
            raise ValueError(f"Recipe migration changed settings: {name}")
        normalized = TypeAdapter(JsonDict).validate_json(
            original.model_dump_json()
        )
        hashes[name] = hashlib.sha256(
            _canonical(normalized).encode()
        ).hexdigest()
    return hashes
