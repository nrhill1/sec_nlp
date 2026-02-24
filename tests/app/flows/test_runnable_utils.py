# tests/app/flows/test_runnable_utils.py
"""Tests for shared flow runnable utility helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sec_nlp.app.flows.models import FlowDefaults, FlowStageSpec
from sec_nlp.app.flows.runnables.utils import (
    build_chat_defaults_payload,
    build_stage_defaults_payload,
    build_stage_result,
    build_unexecuted_stage_result,
    normalize_stage_metadata,
    short_id_or_none,
)
from sec_nlp.core.types import as_json_dict
from sec_nlp.pipelines.presets.retrieve.models import RetrieveResult


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


def test_short_id_or_none_normalizes_non_positive_values() -> None:
    assert short_id_or_none(42) == 42
    assert short_id_or_none(0) is None
    assert short_id_or_none(-1) is None


def test_build_stage_result_converts_paths_and_metadata() -> None:
    stage = FlowStageSpec(
        id="retrieve_seed",
        pipeline="retrieve",
        overrides={},
    )
    pipeline_result = RetrieveResult(
        success=True,
        outputs=[Path("/tmp/output.json")],
        metadata={"path": Path("/tmp/nested.txt")},
        symbols_processed=1,
        queries_processed=1,
        hits_returned=1,
    )

    stage_result = build_stage_result(
        stage=stage,
        pipeline_result=pipeline_result,
        duration_seconds=1.25,
        run_id="run-123",
        run_short_id=0,
    )

    assert stage_result.stage_id == "retrieve_seed"
    assert stage_result.outputs == ["/tmp/output.json"]
    assert stage_result.run_short_id is None
    assert stage_result.metadata["path"] == "/tmp/nested.txt"


def test_build_unexecuted_stage_result_respects_skipped_state() -> None:
    stage = FlowStageSpec(
        id="chat_answer",
        pipeline="chat",
        overrides={},
    )

    missing_seed = build_unexecuted_stage_result(
        stage=stage,
        success=False,
        skipped=False,
        error="Missing seeded artifact",
    )
    skipped = build_unexecuted_stage_result(
        stage=stage,
        success=False,
        skipped=True,
        error="Skipped due to previous stage failure",
    )

    assert missing_seed.success is False
    assert missing_seed.skipped is False
    assert skipped.success is False
    assert skipped.skipped is True
