# tests/app/workspace/test_stage_bindings.py
"""Tests for flow stage input binding validation."""

from __future__ import annotations

import pytest

from sec_nlp.app.workspace.recipes import (
    EvidenceInput,
    RecipeDefaults,
    RecipeStep,
    ResearchRecipe,
)


def test_flow_spec_accepts_single_chat_binding() -> None:
    spec = ResearchRecipe(
        name="single-chat-binding",
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
                overrides={"question": "Summarize with citations."},
            ),
        ],
    )
    assert len(spec.stages[1].inputs) == 1


def test_stage_spec_rejects_invalid_target_field() -> None:
    with pytest.raises(ValueError, match="must be 'seed_context'"):
        ResearchRecipe(
            name="invalid-target-field",
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
                            target_field="invalid_target",
                        )
                    ],
                    overrides={"question": "Summarize with citations."},
                ),
            ],
        )


def test_flow_spec_rejects_multiple_chat_bindings() -> None:
    with pytest.raises(ValueError, match="at most one input binding"):
        ResearchRecipe(
            name="invalid-multiple-bindings",
            defaults=RecipeDefaults(email="test@example.com"),
            stages=[
                RecipeStep(
                    id="retrieve_seed",
                    pipeline="retrieve",
                    overrides={"queries": ["liquidity risk"]},
                ),
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
                            from_stage="retrieve_seed",
                            artifact="retrieve_seed",
                        ),
                        EvidenceInput(
                            from_stage="exhibit_seed",
                            artifact="contract_evidence",
                        ),
                    ],
                    overrides={"question": "Summarize with citations."},
                ),
            ],
        )
