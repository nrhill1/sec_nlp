# tests/app/flows/test_registry.py
"""Tests for flow stage adapter registry dispatch."""

from __future__ import annotations

import pytest

from sec_nlp.app.flows.artifacts import FlowArtifactStore
from sec_nlp.app.flows.models import (
    FlowDefaults,
    FlowSpec,
    FlowStageResult,
    FlowStageSpec,
)
from sec_nlp.app.flows.registry import FlowStageAdapter, resolve_stage_adapter
from sec_nlp.app.flows.runner import FlowRunner


def test_resolve_stage_adapter_for_supported_pipelines() -> None:
    retrieve_adapter = resolve_stage_adapter("retrieve")
    chat_adapter = resolve_stage_adapter("chat")
    exhibit_adapter = resolve_stage_adapter("exhibit")

    assert retrieve_adapter.pipeline == "retrieve"
    assert chat_adapter.pipeline == "chat"
    assert exhibit_adapter.pipeline == "exhibit"


def test_resolve_stage_adapter_rejects_unknown_pipeline() -> None:
    with pytest.raises(ValueError, match="Unsupported flow pipeline"):
        resolve_stage_adapter("unsupported")


def test_flow_runner_uses_registry_for_stage_dispatch(monkeypatch) -> None:
    invoked: list[str] = []

    def _fake_invoke(
        stage: FlowStageSpec,
        defaults: FlowDefaults,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        _ = defaults
        _ = artifacts
        invoked.append(stage.id)
        return FlowStageResult(
            stage_id=stage.id,
            pipeline=stage.pipeline,
            success=True,
            outputs=[],
            metadata={},
        )

    monkeypatch.setattr(
        "sec_nlp.app.flows.runner.resolve_stage_adapter",
        lambda _pipeline: FlowStageAdapter(
            pipeline="retrieve",
            invoke=_fake_invoke,
        ),
    )

    spec = FlowSpec(
        name="registry-dispatch",
        defaults=FlowDefaults(email="test@example.com", symbols=["CDE"]),
        stages=[
            FlowStageSpec(
                id="retrieve_seed",
                pipeline="retrieve",
                overrides={"queries": ["liquidity risk"]},
            )
        ],
    )
    result = FlowRunner(spec=spec).run()

    assert result.success is True
    assert invoked == ["retrieve_seed"]
