# tests/app/flows/test_compiled.py
"""Tests for compile-once flow-stage settings."""

from __future__ import annotations

from pathlib import Path

from sec_nlp.app.flows.artifacts import FlowArtifactStore
from sec_nlp.app.flows.compiled import compile_flow_stages
from sec_nlp.app.flows.contracts import FlowRetrievedChunk, FlowSeedBundle
from sec_nlp.app.flows.models import FlowDefaults, FlowSpec, FlowStageSpec
from sec_nlp.app.flows.runner import FlowRunner
from sec_nlp.pipelines.presets.chat import ChatPipeline, ChatSettings
from sec_nlp.pipelines.presets.chat.models import ChatResult
from sec_nlp.pipelines.presets.exb import ExhibitConfig
from sec_nlp.pipelines.presets.retrieve import RetrieveSettings
from sec_nlp.types import JsonValue


def test_compile_flow_stages_returns_typed_settings() -> None:
    spec = FlowSpec(
        name="compile-typed",
        defaults=FlowDefaults(email="test@example.com"),
        stages=[
            FlowStageSpec(
                id="retrieve_seed",
                pipeline="retrieve",
                overrides={"queries": ["liquidity risk"], "symbols": ["CDE"]},
            ),
            FlowStageSpec(
                id="chat_answer",
                pipeline="chat",
                overrides={
                    "question": "What changed in liquidity risk?",
                    "interactive": False,
                    "symbols": ["CDE"],
                },
            ),
            FlowStageSpec(
                id="exhibit_seed",
                pipeline="exhibit",
                overrides={"dry_run": True, "symbols": ["CDE"]},
            ),
        ],
    )

    compiled = compile_flow_stages(spec)

    assert len(compiled) == 3
    assert isinstance(compiled[0].settings, RetrieveSettings)
    assert isinstance(compiled[1].settings, ChatSettings)
    assert isinstance(compiled[2].settings, ExhibitConfig)
    assert compiled[0].settings.symbols == ["CDE"]
    assert compiled[1].settings.symbols == ["CDE"]
    assert compiled[2].settings.symbols == ["CDE"]


def test_flow_runner_stage_uses_compiled_config_without_revalidation(
    monkeypatch,
) -> None:
    settings = ChatSettings.model_validate(
        {
            "email": "test@example.com",
            "symbols": ["CDE"],
            "question": "What changed in liquidity risk?",
            "interactive": False,
            "output_format": "json",
            "collections": ["retrieve"],
        }
    )
    stage = compile_flow_stages(
        FlowSpec(
            name="compiled-stage",
            defaults=FlowDefaults(email="test@example.com"),
            stages=[
                FlowStageSpec(
                    id="chat_answer",
                    pipeline="chat",
                    overrides={
                        "question": "What changed in liquidity risk?",
                        "interactive": False,
                        "output_format": "json",
                        "collections": ["retrieve"],
                        "symbols": ["CDE"],
                    },
                )
            ],
        )
    )[0]

    def _fail_if_called(*args: JsonValue, **kwargs: JsonValue) -> None:
        _ = (args, kwargs)
        raise AssertionError("ChatSettings.model_validate should not be called")

    monkeypatch.setattr(ChatSettings, "model_validate", _fail_if_called)

    def _fake_chat_run_for_flow(
        self: ChatPipeline,
        *,
        seed_context: FlowSeedBundle | None,
        seed_chunks: tuple[FlowRetrievedChunk, ...],
    ) -> ChatResult:
        _ = (self, seed_context, seed_chunks)
        return ChatResult(
            success=True,
            outputs=[Path("/tmp/chat_summary.json")],
            metadata={"seeded_context": False},
            turns_processed=1,
            hits_retrieved=0,
            citations_returned=0,
            answer="No matching filings.",
            citation_ids=[],
        )

    monkeypatch.setattr(ChatPipeline, "run_for_flow", _fake_chat_run_for_flow)
    # Keep a prevalidated settings instance to ensure stage execution does not
    # call ChatSettings.model_validate again.
    stage = stage.__class__(stage=stage.stage, settings=settings)

    runner = FlowRunner(
        spec=FlowSpec(
            name="compiled-stage",
            defaults=FlowDefaults(email="test@example.com"),
            stages=[
                FlowStageSpec(
                    id="placeholder",
                    pipeline="chat",
                    overrides={
                        "question": "placeholder",
                        "interactive": False,
                        "collections": ["retrieve"],
                        "symbols": ["CDE"],
                    },
                )
            ],
        )
    )
    result = runner._run_stage(stage, FlowArtifactStore())
    assert result.success is True
