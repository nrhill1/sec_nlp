"""Tests for shared flow runnable utility helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sec_nlp.app.flows.models import FlowDefaults
from sec_nlp.app.flows.runnables.utils import (
    build_chat_defaults_payload,
    build_stage_defaults_payload,
    normalize_stage_metadata,
)
from sec_nlp.core.types import as_json_dict


def test_build_stage_defaults_payload_includes_configured_values() -> None:
    defaults = FlowDefaults(
        email="test@example.com",
        symbols=["CDE"],
        forms=["10-K"],
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        dry_run=False,
    )

    payload = build_stage_defaults_payload(defaults)

    assert payload["email"] == "test@example.com"
    assert payload["symbols"] == ["CDE"]
    assert payload["forms"] == ["10-K"]
    assert payload["start_date"] == date(2024, 1, 1)
    assert payload["end_date"] == date(2024, 12, 31)
    assert payload["dry_run"] is False


def test_build_chat_defaults_payload_matches_base_defaults() -> None:
    defaults = FlowDefaults(
        email="test@example.com",
        symbols=["CDE"],
    )

    stage_payload = build_stage_defaults_payload(defaults)
    chat_payload = build_chat_defaults_payload(defaults)

    assert chat_payload == stage_payload


def test_normalize_stage_metadata_converts_paths() -> None:
    metadata = {
        "output": Path("/tmp/result.json"),
        "nested": {"path": Path("/tmp/a.txt"), "count": 2},
        "items": [Path("/tmp/x"), "ok"],
    }

    payload = normalize_stage_metadata(metadata)

    assert payload["output"] == "/tmp/result.json"
    nested_raw = payload.get("nested")
    assert nested_raw is not None
    nested = as_json_dict(nested_raw)
    assert nested is not None
    assert nested["path"] == "/tmp/a.txt"
    items = payload.get("items")
    assert isinstance(items, list)
    assert items[0] == "/tmp/x"
