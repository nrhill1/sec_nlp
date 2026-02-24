# tests/app/flows/test_retrieve_chat_flow.py
"""Tests for retrieve->chat flow runtime orchestration."""

from __future__ import annotations

from pathlib import Path

from sec_nlp.app.flows.models import (
    FlowDefaults,
    FlowSpec,
    FlowStageResult,
    FlowStageSpec,
)
from sec_nlp.app.flows.runner import FlowRunner
from sec_nlp.pipelines.presets.chat import ChatPipeline
from sec_nlp.pipelines.presets.chat.bridge import ChatSeedBundle
from sec_nlp.pipelines.presets.chat.models import ChatResult
from sec_nlp.pipelines.presets.retrieve import RetrievePipeline
from sec_nlp.pipelines.presets.retrieve.bridge import (
    RetrieveChatSeedBundle,
    RetrieveChatSeedChunk,
)
from sec_nlp.pipelines.presets.retrieve.models import RetrieveResult


def test_flow_runner_passes_retrieve_seed_into_chat(monkeypatch) -> None:
    """Flow runner should hand retrieve artifacts to chat in memory."""
    observed: dict[str, object] = {}

    def _fake_retrieve_run_for_flow(
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
                upstream_run_id="00000000-0000-0000-0000-000000000001",
                upstream_short_id=1,
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

    def _fake_chat_run(self: ChatPipeline) -> ChatResult:
        seed = self.config.seed_context
        assert isinstance(seed, ChatSeedBundle)
        observed["seed_upstream_run_id"] = seed.upstream_run_id
        observed["seed_symbols"] = list(seed.symbols)
        observed["seed_queries"] = list(seed.queries)
        return ChatResult(
            success=True,
            outputs=[Path("/tmp/chat_summary.json")],
            metadata={"seeded_context": True},
            turns_processed=1,
            hits_retrieved=1,
            citations_returned=1,
            answer="Liquidity risk increased due to debt costs. [C1]",
            citation_ids=["C1"],
        )

    monkeypatch.setattr(
        RetrievePipeline,
        "run_for_flow",
        _fake_retrieve_run_for_flow,
    )
    monkeypatch.setattr(ChatPipeline, "run", _fake_chat_run)

    spec = FlowSpec(
        name="retrieve-chat-seeded",
        defaults=FlowDefaults(
            email="test@example.com",
            symbols=["CDE"],
        ),
        stages=[
            FlowStageSpec(
                id="retrieve_seed",
                pipeline="retrieve",
                overrides={
                    "queries": ["liquidity risk"],
                    "output_format": "json",
                },
            ),
            FlowStageSpec(
                id="chat_answer",
                pipeline="chat",
                seed_from_stage="retrieve_seed",
                overrides={
                    "question": "What changed in liquidity risk?",
                    "output_format": "json",
                    "interactive": False,
                    "collections": ["retrieve"],
                },
            ),
        ],
    )

    result = FlowRunner(spec=spec).run()

    assert result.success is True
    assert [stage.stage_id for stage in result.stage_results] == [
        "retrieve_seed",
        "chat_answer",
    ]
    chat_stage = result.stage_results[1]
    answer_preview = chat_stage.metadata.get("answer_preview")
    assert isinstance(answer_preview, str)
    assert answer_preview.startswith(
        "Liquidity risk increased due to debt costs."
    )
    assert "\n" not in answer_preview
    duration_value = result.metadata.get("duration_seconds")
    assert isinstance(duration_value, int | float)
    assert float(duration_value) >= 0.0
    assert (
        observed["seed_upstream_run_id"]
        == "00000000-0000-0000-0000-000000000001"
    )
    assert observed["seed_symbols"] == ["CDE"]
    assert observed["seed_queries"] == ["liquidity risk"]


def test_flow_runner_reports_missing_seed_artifact(monkeypatch) -> None:
    """Chat stage should fail clearly when a required seed artifact is absent."""

    def _fake_retrieve_run_for_flow(
        self: RetrievePipeline,
    ) -> tuple[RetrieveResult, RetrieveChatSeedBundle]:
        _ = self
        return (
            RetrieveResult(success=False, error="upstream failed"),
            RetrieveChatSeedBundle(
                upstream_pipeline="retrieve",
                upstream_run_id="00000000-0000-0000-0000-000000000002",
                upstream_short_id=2,
                symbols=[],
                queries=["liquidity risk"],
                chunks=[],
            ),
        )

    monkeypatch.setattr(
        RetrievePipeline,
        "run_for_flow",
        _fake_retrieve_run_for_flow,
    )

    spec = FlowSpec(
        name="retrieve-chat-missing-seed",
        defaults=FlowDefaults(
            email="test@example.com",
            symbols=["CDE"],
        ),
        on_failure="continue",
        stages=[
            FlowStageSpec(
                id="retrieve_seed",
                pipeline="retrieve",
                overrides={
                    "queries": ["liquidity risk"],
                    "output_format": "json",
                },
            ),
            FlowStageSpec(
                id="chat_answer",
                pipeline="chat",
                seed_from_stage="retrieve_seed",
                overrides={
                    "question": "What changed in liquidity risk?",
                    "output_format": "json",
                    "interactive": False,
                    "collections": ["retrieve"],
                },
            ),
        ],
    )

    result = FlowRunner(spec=spec).run()

    assert result.success is False
    assert len(result.stage_results) == 2
    assert result.stage_results[0].success is False
    assert result.stage_results[1].success is False
    assert (
        result.stage_results[1].error
        == "Missing seeded artifact from stage 'retrieve_seed'"
    )


def test_flow_runner_scopes_vector_caches_to_single_flow_run(
    monkeypatch,
) -> None:
    """Flow runs should clear vector runtime caches before and after stages."""
    clear_calls: list[int] = []

    monkeypatch.setattr(
        "sec_nlp.app.flows.runner.clear_runtime_caches",
        lambda: clear_calls.append(1),
    )

    def _fake_run_stage(
        self: FlowRunner,
        stage: FlowStageSpec,
        artifacts: object,
    ) -> FlowStageResult:
        _ = (self, artifacts)
        return FlowStageResult(
            stage_id=stage.id,
            pipeline=stage.pipeline,
            success=True,
            skipped=False,
            duration_seconds=0.0,
            outputs=[],
            metadata={},
        )

    monkeypatch.setattr(FlowRunner, "_run_stage", _fake_run_stage)

    spec = FlowSpec(
        name="cache-scope",
        defaults=FlowDefaults(
            email="test@example.com",
            symbols=["CDE"],
        ),
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
        ],
    )

    result = FlowRunner(spec=spec).run()

    assert result.success is True
    assert len(clear_calls) == 2
