# src/scripts/migrate/flow_defaults_email_only.py
"""Migrate flow specs to email-only defaults with stage-level overrides."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from sec_nlp.pipelines.presets.chat import ChatSettings
from sec_nlp.pipelines.presets.exb import ExhibitConfig
from sec_nlp.pipelines.presets.retrieve import RetrieveSettings

type JsonScalar = str | int | float | bool | None
type JsonLike = JsonScalar | list["JsonLike"] | dict[str, "JsonLike"]

_LEGACY_DEFAULT_KEYS: tuple[str, ...] = (
    "symbols",
    "forms",
    "start_date",
    "end_date",
    "dl_path",
    "out_path",
    "dry_run",
)

_PIPELINE_FIELDS: dict[str, set[str]] = {
    "retrieve": set(RetrieveSettings.model_fields.keys()),
    "chat": set(ChatSettings.model_fields.keys()),
    "exhibit": set(ExhibitConfig.model_fields.keys()),
}


@dataclass(frozen=True, slots=True)
class MigrationStats:
    """Summary counters for one migration run."""

    files_scanned: int = 0
    files_updated: int = 0
    stages_updated: int = 0


def _as_mapping(value: JsonLike | None) -> dict[str, JsonLike]:
    """Return a mutable string-key mapping for YAML object values."""
    if isinstance(value, dict):
        payload: dict[str, JsonLike] = {}
        for key, item in value.items():
            if isinstance(key, str):
                payload[key] = item
        return payload
    return {}


def _as_stage_list(value: JsonLike | None) -> list[dict[str, JsonLike]]:
    """Return stage list as mutable dict entries."""
    if not isinstance(value, list):
        return []
    stages: list[dict[str, JsonLike]] = []
    for item in value:
        if isinstance(item, dict):
            stage_payload: dict[str, JsonLike] = {}
            for key, item_value in item.items():
                if isinstance(key, str):
                    stage_payload[key] = item_value
            stages.append(stage_payload)
    return stages


def migrate_flow_document(
    data: dict[str, JsonLike],
) -> tuple[dict[str, JsonLike], int]:
    """Migrate one loaded flow document and return updated stage count."""
    defaults = _as_mapping(data.get("defaults"))
    email = defaults.get("email")
    if not isinstance(email, str) or not email.strip():
        raise ValueError("Flow defaults must include non-empty email")

    legacy_values: dict[str, JsonLike] = {}
    for key in _LEGACY_DEFAULT_KEYS:
        if key in defaults:
            legacy_values[key] = defaults[key]

    stages = _as_stage_list(data.get("stages"))
    updated_stages = 0
    for stage in stages:
        pipeline_raw = stage.get("pipeline")
        if not isinstance(pipeline_raw, str):
            continue
        pipeline = pipeline_raw.strip().lower()
        pipeline_fields = _PIPELINE_FIELDS.get(pipeline)
        if pipeline_fields is None:
            continue

        overrides = _as_mapping(stage.get("overrides"))
        original_size = len(overrides)
        for key, value in legacy_values.items():
            if key in pipeline_fields and key not in overrides:
                overrides[key] = value

        if len(overrides) != original_size:
            stage["overrides"] = overrides
            updated_stages += 1

    data["defaults"] = {"email": email}
    data["stages"] = stages
    return data, updated_stages


def migrate_flow_file(path: Path) -> tuple[bool, int]:
    """Migrate one YAML flow spec file in place."""
    raw = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw)
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} does not contain a YAML mapping")

    data: dict[str, JsonLike] = {}
    for key, value in loaded.items():
        if isinstance(key, str):
            data[key] = value

    migrated, updated_stages = migrate_flow_document(data)
    rendered = yaml.safe_dump(
        migrated,
        sort_keys=False,
        allow_unicode=True,
    )
    changed = rendered != raw
    if changed:
        path.write_text(rendered, encoding="utf-8")
    return changed, updated_stages


def migrate_flow_tree(root: Path) -> MigrationStats:
    """Migrate every flow YAML under root recursively."""
    files = sorted(root.rglob("*.yaml"))
    stats = MigrationStats(files_scanned=len(files))
    updated_files = 0
    updated_stages = 0
    for file_path in files:
        changed, stage_count = migrate_flow_file(file_path)
        updated_stages += stage_count
        if changed:
            updated_files += 1

    return MigrationStats(
        files_scanned=stats.files_scanned,
        files_updated=updated_files,
        stages_updated=updated_stages,
    )


def main() -> int:
    """Run CLI migration for repository flow jobs."""
    repo_root = Path(__file__).resolve().parents[3]
    flow_root = repo_root / "jobs"
    stats = migrate_flow_tree(flow_root)
    print(
        "migrated flow specs:",
        f"files_scanned={stats.files_scanned}",
        f"files_updated={stats.files_updated}",
        f"stages_updated={stats.stages_updated}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
