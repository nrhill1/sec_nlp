# tests/app/flows/test_stage_bindings.py
"""Tests for flow stage input binding validation."""

from __future__ import annotations

from sec_nlp.app.flows.models import FlowStageInputBinding, FlowStageSpec
from sec_nlp.app.flows.runner import FlowRunner


def test_resolve_seed_binding_accepts_single_supported_binding() -> None:
    stage = FlowStageSpec(
        id="chat_answer",
        pipeline="chat",
        inputs=[
            FlowStageInputBinding(
                from_stage="retrieve_seed",
                artifact="retrieve_seed",
                target_field="seed_context",
            )
        ],
        overrides={},
    )

    binding, error = FlowRunner._resolve_seed_binding(stage)
    assert error is None
    assert binding is not None
    assert binding.from_stage == "retrieve_seed"


def test_resolve_seed_binding_rejects_multiple_bindings() -> None:
    stage = FlowStageSpec(
        id="chat_answer",
        pipeline="chat",
        inputs=[
            FlowStageInputBinding(
                from_stage="retrieve_seed",
                artifact="retrieve_seed",
                target_field="seed_context",
            ),
            FlowStageInputBinding(
                from_stage="exhibit_seed",
                artifact="contract_evidence",
                target_field="seed_context",
            ),
        ],
        overrides={},
    )

    binding, error = FlowRunner._resolve_seed_binding(stage)
    assert binding is None
    assert isinstance(error, str)
    assert "at most one input binding" in error


def test_validate_input_binding_rejects_invalid_target_field() -> None:
    stage = FlowStageSpec(
        id="chat_answer",
        pipeline="chat",
        inputs=[],
        overrides={},
    )
    binding = FlowStageInputBinding(
        from_stage="retrieve_seed",
        artifact="retrieve_seed",
        target_field="invalid_target",
    )

    error = FlowRunner._validate_input_binding(stage=stage, binding=binding)
    assert isinstance(error, str)
    assert "must be 'seed_context'" in error
