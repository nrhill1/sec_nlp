# tests/app/flows/test_flow_spec.py
"""Tests for flow spec validation rules."""

from __future__ import annotations

import pytest

from sec_nlp.app.flows.models import (
    FlowDefaults,
    FlowSpec,
    FlowStageInputBinding,
    FlowStageSpec,
)


def test_flow_spec_seed_stage_must_be_retrieve() -> None:
    with pytest.raises(
        ValueError,
        match="retrieve_seed input must reference a retrieve stage",
    ):
        FlowSpec(
            name="invalid-seed-upstream",
            defaults=FlowDefaults(email="test@example.com"),
            stages=[
                FlowStageSpec(
                    id="chat_seed_source",
                    pipeline="chat",
                    overrides={
                        "question": "What changed in liquidity risk?",
                        "interactive": False,
                    },
                ),
                FlowStageSpec(
                    id="chat_answer",
                    pipeline="chat",
                    inputs=[
                        FlowStageInputBinding(
                            from_stage="chat_seed_source",
                            artifact="retrieve_seed",
                            target_field="seed_context",
                        )
                    ],
                    overrides={
                        "question": "Summarize with citations.",
                        "interactive": False,
                    },
                ),
            ],
        )


def test_flow_spec_allows_chat_seeded_from_retrieve() -> None:
    spec = FlowSpec(
        name="valid-seed-upstream",
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
                        target_field="seed_context",
                    )
                ],
                overrides={
                    "question": "Summarize with citations.",
                    "interactive": False,
                },
            ),
        ],
    )
    assert len(spec.stages[1].inputs) == 1
    assert spec.stages[1].inputs[0].from_stage == "retrieve_seed"
    assert spec.stages[1].inputs[0].artifact == "retrieve_seed"


def test_flow_spec_allows_chat_seeded_with_inputs_binding() -> None:
    spec = FlowSpec(
        name="valid-seed-input-binding",
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
                        target_field="seed_context",
                    )
                ],
                overrides={
                    "question": "Summarize with citations.",
                    "interactive": False,
                },
            ),
        ],
    )
    assert len(spec.stages[1].inputs) == 1
    assert spec.stages[1].inputs[0].target_field == "seed_context"


def test_flow_spec_allows_exhibit_stage() -> None:
    spec = FlowSpec(
        name="exhibit-only",
        defaults=FlowDefaults(email="test@example.com"),
        stages=[
            FlowStageSpec(
                id="exhibit_seed",
                pipeline="exhibit",
                overrides={"output_format": "json"},
            )
        ],
    )
    assert spec.stages[0].pipeline == "exhibit"


def test_flow_spec_allows_chat_contract_input_from_exhibit() -> None:
    spec = FlowSpec(
        name="exhibit-chat-contract-seed",
        defaults=FlowDefaults(email="test@example.com"),
        stages=[
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
                        from_stage="exhibit_seed",
                        artifact="contract_evidence",
                        target_field="seed_context",
                    )
                ],
                overrides={
                    "question": "Summarize key contract obligations.",
                    "interactive": False,
                },
            ),
        ],
    )
    assert len(spec.stages[1].inputs) == 1
    assert spec.stages[1].inputs[0].artifact == "contract_evidence"


def test_flow_spec_rejects_contract_input_from_non_exhibit_stage() -> None:
    with pytest.raises(
        ValueError,
        match="contract_evidence input must reference an exhibit stage",
    ):
        FlowSpec(
            name="invalid-contract-input",
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
                            artifact="contract_evidence",
                        )
                    ],
                    overrides={
                        "question": "Summarize with citations.",
                        "interactive": False,
                    },
                ),
            ],
        )


def test_flow_spec_rejects_inputs_for_non_chat_stage() -> None:
    with pytest.raises(
        ValueError,
        match="does not accept input bindings yet",
    ):
        FlowSpec(
            name="invalid-retrieve-inputs",
            defaults=FlowDefaults(email="test@example.com"),
            stages=[
                FlowStageSpec(
                    id="retrieve_seed",
                    pipeline="retrieve",
                    inputs=[
                        FlowStageInputBinding(
                            from_stage="retrieve_seed",
                            artifact="retrieve_seed",
                        )
                    ],
                    overrides={"queries": ["liquidity risk"]},
                )
            ],
        )


def test_flow_defaults_reject_legacy_non_email_fields() -> None:
    with pytest.raises(ValueError, match="symbols"):
        FlowDefaults.model_validate(
            {
                "email": "test@example.com",
                "symbols": ["CDE"],
            }
        )
