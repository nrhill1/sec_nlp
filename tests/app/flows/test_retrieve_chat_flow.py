# tests/app/flows/test_retrieve_chat_flow.py
"""Tests for retrieve->chat flow runtime orchestration."""

from __future__ import annotations

from pathlib import Path

from sec_nlp.app.flows.artifacts import FlowArtifactStore
from sec_nlp.app.flows.compiled import CompiledStage
from sec_nlp.app.flows.contracts import (
    ContractEvidenceBundle,
)
from sec_nlp.app.flows.models import (
    FlowDefaults,
    FlowSpec,
    FlowStageInputBinding,
    FlowStageResult,
    FlowStageSpec,
)
from sec_nlp.app.flows.runner import FlowRunner
from sec_nlp.pipelines.presets.chat import ChatPipeline
from sec_nlp.pipelines.presets.chat.bridge import (
    ChatRetrievedChunk,
    ChatSeedBundle,
)
from sec_nlp.pipelines.presets.chat.models import ChatResult
from sec_nlp.pipelines.presets.exb import ExhibitPipeline
from sec_nlp.pipelines.presets.exb.models import ExhibitResult
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
    ) -> tuple[
        RetrieveResult,
        RetrieveChatSeedBundle,
        tuple[ChatRetrievedChunk, ...],
    ]:
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
            (
                ChatRetrievedChunk(
                    collection="retrieve",
                    score=0.9,
                    symbol="CDE",
                    accession_number="0000215466-24-000003",
                    form_type="10-K",
                    filed_date="2024-02-21",
                    source="https://www.sec.gov/ixviewer/ix.html",
                    snippet="Liquidity risk increased in fiscal year 2024.",
                    vector=None,
                ),
            ),
        )

    def _fake_chat_run_for_flow(
        self: ChatPipeline,
        *,
        seed_context: ChatSeedBundle | None,
        seed_chunks: tuple[ChatRetrievedChunk, ...],
    ) -> ChatResult:
        _ = (self, seed_chunks)
        seed = seed_context
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
        "run_for_flow_with_chunks",
        _fake_retrieve_run_for_flow,
    )
    monkeypatch.setattr(ChatPipeline, "run_for_flow", _fake_chat_run_for_flow)

    spec = FlowSpec(
        name="retrieve-chat-seeded",
        defaults=FlowDefaults(email="test@example.com"),
        stages=[
            FlowStageSpec(
                id="retrieve_seed",
                pipeline="retrieve",
                overrides={
                    "queries": ["liquidity risk"],
                    "output_format": "json",
                    "symbols": ["CDE"],
                },
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
                    "question": "What changed in liquidity risk?",
                    "output_format": "json",
                    "interactive": False,
                    "collections": ["retrieve"],
                    "symbols": ["CDE"],
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


def test_flow_runner_passes_seed_via_inputs_binding(monkeypatch) -> None:
    """Flow runner should resolve seeded chat context from `inputs` binding."""
    observed: dict[str, object] = {}

    def _fake_retrieve_run_for_flow(
        self: RetrievePipeline,
    ) -> tuple[
        RetrieveResult,
        RetrieveChatSeedBundle,
        tuple[ChatRetrievedChunk, ...],
    ]:
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
                upstream_run_id="00000000-0000-0000-0000-000000000003",
                upstream_short_id=3,
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
            (
                ChatRetrievedChunk(
                    collection="retrieve",
                    score=0.9,
                    symbol="CDE",
                    accession_number="0000215466-24-000003",
                    form_type="10-K",
                    filed_date="2024-02-21",
                    source="https://www.sec.gov/ixviewer/ix.html",
                    snippet="Liquidity risk increased in fiscal year 2024.",
                    vector=None,
                ),
            ),
        )

    def _fake_chat_run_for_flow(
        self: ChatPipeline,
        *,
        seed_context: ChatSeedBundle | None,
        seed_chunks: tuple[ChatRetrievedChunk, ...],
    ) -> ChatResult:
        _ = (self, seed_chunks)
        seed = seed_context
        assert isinstance(seed, ChatSeedBundle)
        observed["seed_upstream_run_id"] = seed.upstream_run_id
        return ChatResult(
            success=True,
            outputs=[Path("/tmp/chat_summary.json")],
            metadata={"seeded_context": True},
            turns_processed=1,
            hits_retrieved=1,
            citations_returned=1,
            answer="Answer. [C1]",
            citation_ids=["C1"],
        )

    monkeypatch.setattr(
        RetrievePipeline,
        "run_for_flow_with_chunks",
        _fake_retrieve_run_for_flow,
    )
    monkeypatch.setattr(ChatPipeline, "run_for_flow", _fake_chat_run_for_flow)

    spec = FlowSpec(
        name="retrieve-chat-seeded-inputs",
        defaults=FlowDefaults(email="test@example.com"),
        stages=[
            FlowStageSpec(
                id="retrieve_seed",
                pipeline="retrieve",
                overrides={
                    "queries": ["liquidity risk"],
                    "output_format": "json",
                    "symbols": ["CDE"],
                },
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
                    "question": "What changed in liquidity risk?",
                    "output_format": "json",
                    "interactive": False,
                    "collections": ["retrieve"],
                    "symbols": ["CDE"],
                },
            ),
        ],
    )

    result = FlowRunner(spec=spec).run()

    assert result.success is True
    assert observed["seed_upstream_run_id"] == (
        "00000000-0000-0000-0000-000000000003"
    )


def test_flow_runner_reports_missing_seed_artifact(monkeypatch) -> None:
    """Chat stage should fail clearly when a required seed artifact is absent."""

    def _fake_retrieve_run_for_flow(
        self: RetrievePipeline,
    ) -> tuple[
        RetrieveResult,
        RetrieveChatSeedBundle,
        tuple[ChatRetrievedChunk, ...],
    ]:
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
            (),
        )

    monkeypatch.setattr(
        RetrievePipeline,
        "run_for_flow_with_chunks",
        _fake_retrieve_run_for_flow,
    )

    spec = FlowSpec(
        name="retrieve-chat-missing-seed",
        defaults=FlowDefaults(email="test@example.com"),
        on_failure="continue",
        stages=[
            FlowStageSpec(
                id="retrieve_seed",
                pipeline="retrieve",
                overrides={
                    "queries": ["liquidity risk"],
                    "output_format": "json",
                    "symbols": ["CDE"],
                },
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
                    "question": "What changed in liquidity risk?",
                    "output_format": "json",
                    "interactive": False,
                    "collections": ["retrieve"],
                    "symbols": ["CDE"],
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
        == "Missing retrieve_seed artifact from stage 'retrieve_seed'"
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
        stage: CompiledStage,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        _ = (self, artifacts)
        return FlowStageResult(
            stage_id=stage.stage.id,
            pipeline=stage.stage.pipeline,
            success=True,
            skipped=False,
            duration_seconds=0.0,
            outputs=[],
            metadata={},
        )

    monkeypatch.setattr(FlowRunner, "_run_stage", _fake_run_stage)

    spec = FlowSpec(
        name="cache-scope",
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
        ],
    )

    result = FlowRunner(spec=spec).run()

    assert result.success is True
    assert len(clear_calls) == 2


def test_flow_runner_executes_exhibit_stage(monkeypatch) -> None:
    """Flow runner should execute exhibit stage via runnable dispatch."""

    def _fake_exhibit_run_for_flow(
        self: ExhibitPipeline,
    ) -> tuple[
        ExhibitResult, ContractEvidenceBundle, tuple[ChatRetrievedChunk, ...]
    ]:
        _ = self
        return (
            ExhibitResult(
                success=True,
                outputs=[Path("/tmp/exhibit_summary.yaml")],
                metadata={"chunks_indexed": 3},
            ),
            ContractEvidenceBundle(
                upstream_pipeline="exhibit",
                upstream_run_id="00000000-0000-0000-0000-000000000401",
                upstream_short_id=401,
                symbols=["CDE"],
                queries=["supply agreement"],
                chunks=[],
            ),
            (),
        )

    monkeypatch.setattr(
        ExhibitPipeline,
        "run_for_flow_with_chunks",
        _fake_exhibit_run_for_flow,
    )

    spec = FlowSpec(
        name="exhibit-only",
        defaults=FlowDefaults(email="test@example.com"),
        stages=[
            FlowStageSpec(
                id="exhibit_seed",
                pipeline="exhibit",
                overrides={
                    "output_format": "json",
                    "dry_run": True,
                    "symbols": ["CDE"],
                },
            ),
        ],
    )

    result = FlowRunner(spec=spec).run()

    assert result.success is True
    assert len(result.stage_results) == 1
    assert result.stage_results[0].stage_id == "exhibit_seed"
    assert result.stage_results[0].pipeline == "exhibit"


def test_flow_runner_passes_contract_evidence_into_chat(monkeypatch) -> None:
    """Flow runner should map exhibit contract evidence into chat seed context."""
    observed: dict[str, object] = {}

    def _fake_exhibit_run_for_flow(
        self: ExhibitPipeline,
    ) -> tuple[
        ExhibitResult, ContractEvidenceBundle, tuple[ChatRetrievedChunk, ...]
    ]:
        _ = self
        return (
            ExhibitResult(
                success=True,
                outputs=[Path("/tmp/exhibit_summary.yaml")],
                metadata={"chunks_indexed": 1},
            ),
            ContractEvidenceBundle(
                upstream_pipeline="exhibit",
                upstream_run_id="00000000-0000-0000-0000-000000000402",
                upstream_short_id=402,
                symbols=["CDE"],
                queries=["supply agreement"],
                chunks=[],
            ),
            (
                ChatRetrievedChunk(
                    collection="exhibit",
                    score=0.87,
                    symbol="CDE",
                    accession_number="0000215466-24-000003",
                    form_type="8-K",
                    filed_date="2024-02-21",
                    source="https://www.sec.gov/ixviewer/ix.html",
                    snippet="Supplier must provide NdPr oxide volumes quarterly.",
                    vector=None,
                ),
            ),
        )

    def _fake_chat_run_for_flow(
        self: ChatPipeline,
        *,
        seed_context: ChatSeedBundle | None,
        seed_chunks: tuple[ChatRetrievedChunk, ...],
    ) -> ChatResult:
        _ = self
        seed = seed_context
        assert isinstance(seed, ChatSeedBundle)
        assert seed_chunks
        observed["seed_source"] = seed.upstream_pipeline
        observed["seed_run_id"] = seed.upstream_run_id
        observed["seed_chunk_collection"] = seed_chunks[0].collection
        observed["seed_chunk_score"] = seed_chunks[0].score
        return ChatResult(
            success=True,
            outputs=[Path("/tmp/chat_summary.json")],
            metadata={"seeded_context": True},
            turns_processed=1,
            hits_retrieved=1,
            citations_returned=1,
            answer="Contract includes quarterly delivery obligations. [C1]",
            citation_ids=["C1"],
        )

    monkeypatch.setattr(
        ExhibitPipeline,
        "run_for_flow_with_chunks",
        _fake_exhibit_run_for_flow,
    )
    monkeypatch.setattr(ChatPipeline, "run_for_flow", _fake_chat_run_for_flow)

    spec = FlowSpec(
        name="exhibit-chat-contract-seed",
        defaults=FlowDefaults(email="test@example.com"),
        stages=[
            FlowStageSpec(
                id="exhibit_seed",
                pipeline="exhibit",
                overrides={
                    "output_format": "json",
                    "dry_run": True,
                    "symbols": ["CDE"],
                },
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
                    "question": "Summarize material delivery obligations.",
                    "interactive": False,
                    "output_format": "json",
                    "symbols": ["CDE"],
                },
            ),
        ],
    )

    result = FlowRunner(spec=spec).run()

    assert result.success is True
    assert observed["seed_source"] == "exhibit"
    assert observed["seed_run_id"] == "00000000-0000-0000-0000-000000000402"
    assert observed["seed_chunk_collection"] == "exhibit"
    assert observed["seed_chunk_score"] == 0.87
