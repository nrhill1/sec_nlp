# tests/app/flows/test_runnable_interfaces.py
"""Tests for flow runnable interface contracts."""

from __future__ import annotations

from pathlib import Path

from langchain_core.runnables import RunnableSerializable

from sec_nlp.app.flows.artifacts import FlowArtifactStore
from sec_nlp.app.flows.models import FlowDefaults, FlowStageSpec
from sec_nlp.app.flows.runnables.chat import (
    ChatFlowInvokeInput,
    ChatFlowRunnable,
)
from sec_nlp.app.flows.runnables.retrieve import (
    RetrieveFlowInvokeInput,
    RetrieveFlowRunnable,
)
from sec_nlp.pipelines.presets.chat import ChatPipeline
from sec_nlp.pipelines.presets.chat.models import ChatResult
from sec_nlp.pipelines.presets.retrieve import RetrievePipeline
from sec_nlp.pipelines.presets.retrieve.bridge import (
    RetrieveChatSeedBundle,
    RetrieveChatSeedChunk,
)
from sec_nlp.pipelines.presets.retrieve.models import RetrieveResult


def _flow_defaults() -> FlowDefaults:
    return FlowDefaults(email="test@example.com", symbols=["CDE"])


def test_retrieve_flow_runnable_is_runnable_serializable() -> None:
    assert issubclass(RetrieveFlowRunnable, RunnableSerializable)


def test_chat_flow_runnable_is_runnable_serializable() -> None:
    assert issubclass(ChatFlowRunnable, RunnableSerializable)


def test_retrieve_flow_runnable_invoke_uses_typed_input(monkeypatch) -> None:
    def _fake_run_for_flow(
        self: RetrievePipeline,
    ) -> tuple[RetrieveResult, RetrieveChatSeedBundle]:
        _ = self
        return (
            RetrieveResult(
                success=True,
                outputs=[Path("/tmp/retrieve_summary.json")],
                metadata={"hits_returned": 1},
                symbols_processed=1,
                queries_processed=1,
                hits_returned=1,
            ),
            RetrieveChatSeedBundle(
                upstream_pipeline="retrieve",
                upstream_run_id="00000000-0000-0000-0000-000000000101",
                upstream_short_id=101,
                symbols=["CDE"],
                queries=["liquidity risk"],
                chunks=[
                    RetrieveChatSeedChunk(
                        collection="retrieve",
                        symbol="CDE",
                        accession_number="0000215466-24-000003",
                        form_type="10-K",
                        filed_date="2024-02-21",
                        source="https://www.sec.gov/ixviewer/ix.html",
                        score=0.9,
                        snippet="Liquidity risk increased in fiscal year 2024.",
                    )
                ],
            ),
        )

    monkeypatch.setattr(RetrievePipeline, "run_for_flow", _fake_run_for_flow)

    runnable = RetrieveFlowRunnable(
        stage=FlowStageSpec(
            id="retrieve_seed",
            pipeline="retrieve",
            overrides={"queries": ["liquidity risk"], "output_format": "json"},
        ),
        defaults=_flow_defaults(),
        artifacts=FlowArtifactStore(),
    )

    result = runnable.invoke(RetrieveFlowInvokeInput())

    assert result.success is True
    assert result.stage_id == "retrieve_seed"
    assert result.pipeline == "retrieve"


def test_chat_flow_runnable_invoke_uses_typed_input(monkeypatch) -> None:
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
            overrides={
                "question": "What changed in liquidity risk?",
                "interactive": False,
                "output_format": "json",
                "collections": ["retrieve"],
            },
        ),
        defaults=_flow_defaults(),
        artifacts=FlowArtifactStore(),
    )

    result = runnable.invoke(ChatFlowInvokeInput())

    assert result.success is True
    assert result.stage_id == "chat_answer"
    assert result.pipeline == "chat"
