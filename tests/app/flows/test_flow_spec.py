# tests/app/flows/test_flow_spec.py
"""Tests for flow spec validation rules."""

from __future__ import annotations

import pytest

from sec_nlp.app.flows.models import FlowDefaults, FlowSpec, FlowStageSpec


def test_flow_spec_seed_stage_must_be_retrieve() -> None:
    with pytest.raises(
        ValueError,
        match="seed_from_stage must reference a retrieve stage",
    ):
        FlowSpec(
            name="invalid-seed-upstream",
            defaults=FlowDefaults(email="test@example.com", symbols=["CDE"]),
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
                    seed_from_stage="chat_seed_source",
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
        defaults=FlowDefaults(email="test@example.com", symbols=["CDE"]),
        stages=[
            FlowStageSpec(
                id="retrieve_seed",
                pipeline="retrieve",
                overrides={"queries": ["liquidity risk"]},
            ),
            FlowStageSpec(
                id="chat_answer",
                pipeline="chat",
                seed_from_stage="retrieve_seed",
                overrides={
                    "question": "Summarize with citations.",
                    "interactive": False,
                },
            ),
        ],
    )
    assert spec.stages[1].seed_from_stage == "retrieve_seed"


def test_flow_spec_allows_exhibit_stage() -> None:
    spec = FlowSpec(
        name="exhibit-only",
        defaults=FlowDefaults(email="test@example.com", symbols=["CDE"]),
        stages=[
            FlowStageSpec(
                id="exhibit_seed",
                pipeline="exhibit",
                overrides={"output_format": "json"},
            )
        ],
    )
    assert spec.stages[0].pipeline == "exhibit"
