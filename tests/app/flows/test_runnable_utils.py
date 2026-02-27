# tests/app/flows/test_runnable_utils.py
"""Tests for flow compile and runner utility helpers."""

from __future__ import annotations

from pathlib import Path

from sec_nlp.app.flows.compiled import compile_stage
from sec_nlp.app.flows.models import FlowDefaults, FlowStageSpec
from sec_nlp.app.flows.runner import FlowRunner
from sec_nlp.core.types import as_json_dict, coerce_result_json_dict
from sec_nlp.pipelines.presets.retrieve import RetrieveSettings
from sec_nlp.pipelines.presets.retrieve.models import RetrieveResult


def test_compile_stage_applies_email_default() -> None:
    defaults = FlowDefaults(email="test@example.com")
    stage = FlowStageSpec(
        id="retrieve_seed",
        pipeline="retrieve",
        overrides={},
    )

    compiled = compile_stage(stage=stage, defaults=defaults)

    settings = compiled.settings
    assert isinstance(settings, RetrieveSettings)
    assert settings.email == "test@example.com"


def test_coerce_result_json_dict_converts_paths() -> None:
    metadata = {
        "output": Path("/tmp/result.json"),
        "nested": {"path": Path("/tmp/a.txt"), "count": 2},
        "items": [Path("/tmp/x"), "ok"],
    }

    payload = coerce_result_json_dict(metadata)

    assert payload["output"] == "/tmp/result.json"
    nested_raw = payload.get("nested")
    assert nested_raw is not None
    nested = as_json_dict(nested_raw)
    assert nested is not None
    assert nested["path"] == "/tmp/a.txt"
    items = payload.get("items")
    assert isinstance(items, list)
    assert items[0] == "/tmp/x"


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

    stage_result = FlowRunner._build_stage_result(
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


def test_build_stage_result_retains_positive_short_id() -> None:
    stage = FlowStageSpec(
        id="retrieve_seed",
        pipeline="retrieve",
        overrides={},
    )
    pipeline_result = RetrieveResult(
        success=True,
        outputs=[],
        metadata={},
        symbols_processed=1,
        queries_processed=1,
        hits_returned=1,
    )

    stage_result = FlowRunner._build_stage_result(
        stage=stage,
        pipeline_result=pipeline_result,
        duration_seconds=0.1,
        run_id="run-123",
        run_short_id=42,
    )

    assert stage_result.run_short_id == 42


def test_build_unexecuted_stage_result_respects_skipped_state() -> None:
    stage = FlowStageSpec(
        id="chat_answer",
        pipeline="chat",
        overrides={},
    )

    missing_seed = FlowRunner._build_unexecuted_stage_result(
        stage=stage,
        success=False,
        skipped=False,
        error="Missing seeded artifact",
    )
    skipped = FlowRunner._build_unexecuted_stage_result(
        stage=stage,
        success=False,
        skipped=True,
        error="Skipped due to previous stage failure",
    )

    assert missing_seed.success is False
    assert missing_seed.skipped is False
    assert skipped.success is False
    assert skipped.skipped is True
