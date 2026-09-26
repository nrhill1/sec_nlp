# tests/app/workspace/test_recipe_spec.py
"""Tests for flow spec validation rules."""

from __future__ import annotations

import pytest

from sec_nlp.app.workspace.recipes import (
    EvidenceInput,
    RecipeDefaults,
    RecipeStep,
    ResearchRecipe,
)


def test_flow_spec_seed_stage_must_be_retrieve() -> None:
    with pytest.raises(
        ValueError,
        match="retrieve_seed input must reference a retrieve stage",
    ):
        ResearchRecipe(
            name="invalid-seed-upstream",
            defaults=RecipeDefaults(email="test@example.com"),
            stages=[
                RecipeStep(
                    id="chat_seed_source",
                    pipeline="chat",
                    overrides={
                        "question": "What changed in liquidity risk?",
                        "interactive": False,
                    },
                ),
                RecipeStep(
                    id="chat_answer",
                    pipeline="chat",
                    inputs=[
                        EvidenceInput(
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
    spec = ResearchRecipe(
        name="valid-seed-upstream",
        defaults=RecipeDefaults(email="test@example.com"),
        stages=[
            RecipeStep(
                id="retrieve_seed",
                pipeline="retrieve",
                overrides={"queries": ["liquidity risk"]},
            ),
            RecipeStep(
                id="chat_answer",
                pipeline="chat",
                inputs=[
                    EvidenceInput(
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
    spec = ResearchRecipe(
        name="valid-seed-input-binding",
        defaults=RecipeDefaults(email="test@example.com"),
        stages=[
            RecipeStep(
                id="retrieve_seed",
                pipeline="retrieve",
                overrides={"queries": ["liquidity risk"]},
            ),
            RecipeStep(
                id="chat_answer",
                pipeline="chat",
                inputs=[
                    EvidenceInput(
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
    spec = ResearchRecipe(
        name="exhibit-only",
        defaults=RecipeDefaults(email="test@example.com"),
        stages=[
            RecipeStep(
                id="exhibit_seed",
                pipeline="exhibit",
                overrides={"output_format": "json"},
            )
        ],
    )
    assert spec.stages[0].pipeline == "exhibit"


def test_flow_spec_allows_chat_contract_input_from_exhibit() -> None:
    spec = ResearchRecipe(
        name="exhibit-chat-contract-seed",
        defaults=RecipeDefaults(email="test@example.com"),
        stages=[
            RecipeStep(
                id="exhibit_seed",
                pipeline="exhibit",
                overrides={"dry_run": True},
            ),
            RecipeStep(
                id="chat_answer",
                pipeline="chat",
                inputs=[
                    EvidenceInput(
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
        ResearchRecipe(
            name="invalid-contract-input",
            defaults=RecipeDefaults(email="test@example.com"),
            stages=[
                RecipeStep(
                    id="retrieve_seed",
                    pipeline="retrieve",
                    overrides={"queries": ["liquidity risk"]},
                ),
                RecipeStep(
                    id="chat_answer",
                    pipeline="chat",
                    inputs=[
                        EvidenceInput(
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
        ResearchRecipe(
            name="invalid-retrieve-inputs",
            defaults=RecipeDefaults(email="test@example.com"),
            stages=[
                RecipeStep(
                    id="retrieve_seed",
                    pipeline="retrieve",
                    inputs=[
                        EvidenceInput(
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
        RecipeDefaults.model_validate(
            {
                "email": "test@example.com",
                "symbols": ["CDE"],
            }
        )
