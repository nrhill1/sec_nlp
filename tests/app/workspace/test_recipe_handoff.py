# tests/app/workspace/test_recipe_handoff.py
"""Tests preserving retrieve/exhibit evidence handoff and recipe output metadata."""

from pathlib import Path

import pytest

from sec_nlp.app.workspace.evidence import ContractEvidenceBundle
from sec_nlp.app.workspace.recipes import (
    EvidenceInput,
    RecipeDefaults,
    RecipeStep,
    ResearchRecipe,
    run_recipe,
)
from sec_nlp.pipelines.presets.chat.bridge import (
    ChatRetrievedChunk,
    ChatSeedBundle,
)
from sec_nlp.pipelines.presets.chat.models import ChatResult
from sec_nlp.pipelines.presets.chat.pipeline import ChatPipeline
from sec_nlp.pipelines.presets.exb.models import ExhibitResult
from sec_nlp.pipelines.presets.exb.pipeline import ExhibitPipeline
from sec_nlp.pipelines.presets.retrieve.bridge import (
    RetrieveChatSeedBundle,
    RetrieveChatSeedChunk,
)
from sec_nlp.pipelines.presets.retrieve.models import RetrieveResult
from sec_nlp.pipelines.presets.retrieve.pipeline import RetrievePipeline
from sec_nlp.types import JsonDict


@pytest.fixture(autouse=True)
def _recipe_outputs(tmp_path, monkeypatch):
    """Keep executed recipe artifacts inside each test directory."""
    monkeypatch.setattr("sec_nlp.core.infra.settings.DATA_DIR", tmp_path)


def test_flow_runner_passes_retrieve_seed_into_chat(monkeypatch) -> None:
    """Flow runner should hand retrieve artifacts to chat in memory."""
    observed: JsonDict = {}

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

    spec = ResearchRecipe(
        name="retrieve-chat-seeded",
        defaults=RecipeDefaults(email="test@example.com"),
        stages=[
            RecipeStep(
                id="retrieve_seed",
                pipeline="retrieve",
                overrides={
                    "queries": ["liquidity risk"],
                    "output_format": "json",
                    "symbols": ["CDE"],
                },
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
                    "question": "What changed in liquidity risk?",
                    "output_format": "json",
                    "interactive": False,
                    "collections": ["retrieve"],
                    "symbols": ["CDE"],
                },
            ),
        ],
    )

    result = run_recipe(spec)

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
    answer_output_paths = chat_stage.metadata.get("answer_output_paths")
    assert answer_output_paths == ["/tmp/chat_summary.json"]
    duration_value = result.metadata.get("duration_seconds")
    assert isinstance(duration_value, int | float)
    assert float(duration_value) >= 0.0
    assert result.metadata.get("answer_output_paths") == [
        "/tmp/chat_summary.json"
    ]
    assert (
        observed["seed_upstream_run_id"]
        == "00000000-0000-0000-0000-000000000001"
    )
    assert observed["seed_symbols"] == ["CDE"]
    assert observed["seed_queries"] == ["liquidity risk"]


def test_flow_runner_passes_seed_via_inputs_binding(monkeypatch) -> None:
    """Flow runner should resolve seeded chat context from `inputs` binding."""
    observed: JsonDict = {}

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

    spec = ResearchRecipe(
        name="retrieve-chat-seeded-inputs",
        defaults=RecipeDefaults(email="test@example.com"),
        stages=[
            RecipeStep(
                id="retrieve_seed",
                pipeline="retrieve",
                overrides={
                    "queries": ["liquidity risk"],
                    "output_format": "json",
                    "symbols": ["CDE"],
                },
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
                    "question": "What changed in liquidity risk?",
                    "output_format": "json",
                    "interactive": False,
                    "collections": ["retrieve"],
                    "symbols": ["CDE"],
                },
            ),
        ],
    )

    result = run_recipe(spec)

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

    spec = ResearchRecipe(
        name="retrieve-chat-missing-seed",
        defaults=RecipeDefaults(email="test@example.com"),
        on_failure="continue",
        stages=[
            RecipeStep(
                id="retrieve_seed",
                pipeline="retrieve",
                overrides={
                    "queries": ["liquidity risk"],
                    "output_format": "json",
                    "symbols": ["CDE"],
                },
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
                    "question": "What changed in liquidity risk?",
                    "output_format": "json",
                    "interactive": False,
                    "collections": ["retrieve"],
                    "symbols": ["CDE"],
                },
            ),
        ],
    )

    result = run_recipe(spec)

    assert result.success is False
    assert len(result.stage_results) == 2
    assert result.stage_results[0].success is False
    assert result.stage_results[1].success is False
    assert (
        result.stage_results[1].error
        == "Missing retrieve_seed artifact from stage 'retrieve_seed'"
    )


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

    spec = ResearchRecipe(
        name="exhibit-only",
        defaults=RecipeDefaults(email="test@example.com"),
        stages=[
            RecipeStep(
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

    result = run_recipe(spec)

    assert result.success is True
    assert len(result.stage_results) == 1
    assert result.stage_results[0].stage_id == "exhibit_seed"
    assert result.stage_results[0].pipeline == "exhibit"


def test_flow_runner_passes_contract_evidence_into_chat(monkeypatch) -> None:
    """Flow runner should map exhibit contract evidence into chat seed context."""
    observed: JsonDict = {}

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

    spec = ResearchRecipe(
        name="exhibit-chat-contract-seed",
        defaults=RecipeDefaults(email="test@example.com"),
        stages=[
            RecipeStep(
                id="exhibit_seed",
                pipeline="exhibit",
                overrides={
                    "output_format": "json",
                    "dry_run": True,
                    "symbols": ["CDE"],
                },
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
                    "question": "Summarize material delivery obligations.",
                    "interactive": False,
                    "output_format": "json",
                    "symbols": ["CDE"],
                },
            ),
        ],
    )

    result = run_recipe(spec)

    assert result.success is True
    assert observed["seed_source"] == "exhibit"
    assert observed["seed_run_id"] == "00000000-0000-0000-0000-000000000402"
    assert observed["seed_chunk_collection"] == "exhibit"
    assert observed["seed_chunk_score"] == 0.87


def test_flow_runner_writes_flow_settings_snapshot(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Flow runner should emit a top-level flow settings artifact."""

    def _fake_chat_run_for_flow(
        self: ChatPipeline,
        *,
        seed_context: ChatSeedBundle | None,
        seed_chunks: tuple[ChatRetrievedChunk, ...],
    ) -> ChatResult:
        _ = (self, seed_context, seed_chunks)
        return ChatResult(
            success=True,
            outputs=[Path("/tmp/chat_summary.json")],
            metadata={},
            turns_processed=1,
            hits_retrieved=0,
            citations_returned=0,
            answer="Answer. [C1]",
            citation_ids=["C1"],
        )

    monkeypatch.setattr(ChatPipeline, "_build_components", lambda self: None)
    monkeypatch.setattr(ChatPipeline, "run_for_flow", _fake_chat_run_for_flow)

    spec = ResearchRecipe(
        name="flow-settings-smoke",
        defaults=RecipeDefaults(email="test@example.com"),
        stages=[
            RecipeStep(
                id="chat_answer",
                pipeline="chat",
                overrides={
                    "question": "What changed?",
                    "output_format": "json",
                    "interactive": False,
                    "collections": ["retrieve"],
                    "symbols": ["CDE"],
                    "out_path": str(tmp_path / "outputs"),
                },
            )
        ],
    )

    result = run_recipe(spec)

    assert result.success is True
    snapshot_value = result.metadata.get("flow_settings_snapshot")
    assert isinstance(snapshot_value, str)
    assert snapshot_value.endswith("_settings.json")
    assert snapshot_value in result.outputs
    assert Path(snapshot_value).exists() is True
