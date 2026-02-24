# tests/app/flows/test_compiled.py
"""Tests for compile-once flow-stage settings."""

from __future__ import annotations

from pathlib import Path

from sec_nlp.app.flows.artifacts import FlowArtifactStore
from sec_nlp.app.flows.compiled import compile_flow_stages
from sec_nlp.app.flows.models import FlowDefaults, FlowSpec, FlowStageSpec
from sec_nlp.app.flows.runnables.chat import ChatFlowRunnable
from sec_nlp.pipelines.presets.chat import ChatPipeline, ChatSettings
from sec_nlp.pipelines.presets.chat.models import ChatResult
from sec_nlp.pipelines.presets.exb import ExhibitConfig
from sec_nlp.pipelines.presets.retrieve import RetrieveSettings
from sec_nlp.types import JsonValue


def test_compile_flow_stages_returns_typed_settings() -> None:
    spec = FlowSpec(
        name="compile-typed",
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
                overrides={
                    "question": "What changed in liquidity risk?",
                    "interactive": False,
                },
            ),
            FlowStageSpec(
                id="exhibit_seed",
                pipeline="exhibit",
                overrides={"dry_run": True},
            ),
        ],
    )

    compiled = compile_flow_stages(spec)

    assert len(compiled) == 3
    assert isinstance(compiled[0].settings, RetrieveSettings)
    assert isinstance(compiled[1].settings, ChatSettings)
    assert isinstance(compiled[2].settings, ExhibitConfig)


def test_chat_runnable_uses_compiled_config_without_revalidation(
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

    def _fail_if_called(*args: JsonValue, **kwargs: JsonValue) -> None:
        _ = (args, kwargs)
        raise AssertionError("ChatSettings.model_validate should not be called")

    monkeypatch.setattr(ChatSettings, "model_validate", _fail_if_called)

    def _fake_chat_run(self: ChatPipeline) -> ChatResult:
        _ = self
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

    monkeypatch.setattr(ChatPipeline, "run", _fake_chat_run)

    runnable = ChatFlowRunnable(
        stage=FlowStageSpec(
            id="chat_answer",
            pipeline="chat",
            overrides={},
        ),
        artifacts=FlowArtifactStore(),
        compiled_config=settings,
    )

    result = runnable.invoke()
    assert result.success is True
