# tests/app/flows/test_stage_bindings.py
"""Tests for flow stage input binding validation."""

from __future__ import annotations

import pytest

from sec_nlp.app.flows.models import (
    FlowDefaults,
    FlowSpec,
    FlowStageInputBinding,
    FlowStageSpec,
)
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

    binding = FlowRunner._resolve_seed_binding(stage)
    assert binding is not None
    assert binding.from_stage == "retrieve_seed"


def test_resolve_seed_binding_returns_none_when_empty() -> None:
    stage = FlowStageSpec(id="chat_answer", pipeline="chat", overrides={})
    assert FlowRunner._resolve_seed_binding(stage) is None


def test_stage_spec_rejects_invalid_target_field() -> None:
    with pytest.raises(ValueError, match="must be 'seed_context'"):
        FlowSpec(
            name="invalid-target-field",
            defaults=FlowDefaults(email="test@example.com"),
            stages=[
                FlowStageSpec(
                    id="retrieve_seed",
                    pipeline="retrieve",
                    overrides={"queries": ["liquidity risk"]},
                ),
                FlowStageSpec(
                    id="chat_answer",
                    pipeline="chat",
                    inputs=[
                        FlowStageInputBinding(
                            from_stage="retrieve_seed",
                            artifact="retrieve_seed",
                            target_field="invalid_target",
                        )
                    ],
                    overrides={"question": "Summarize with citations."},
                ),
            ],
        )


def test_flow_spec_rejects_multiple_chat_bindings() -> None:
    with pytest.raises(ValueError, match="at most one input binding"):
        FlowSpec(
            name="invalid-multiple-bindings",
            defaults=FlowDefaults(email="test@example.com"),
            stages=[
                FlowStageSpec(
                    id="retrieve_seed",
                    pipeline="retrieve",
                    overrides={"queries": ["liquidity risk"]},
                ),
                FlowStageSpec(
                    id="exhibit_seed",
                    pipeline="exhibit",
                    overrides={"dry_run": True},
                ),
                FlowStageSpec(
                    id="chat_answer",
                    pipeline="chat",
                    inputs=[
                        FlowStageInputBinding(
                            from_stage="retrieve_seed",
                            artifact="retrieve_seed",
                        ),
                        FlowStageInputBinding(
                            from_stage="exhibit_seed",
                            artifact="contract_evidence",
                        ),
                    ],
                    overrides={"question": "Summarize with citations."},
                ),
            ],
        )
