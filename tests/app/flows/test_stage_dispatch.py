# tests/app/flows/test_stage_dispatch.py
"""Tests for direct stage dispatch in the flow runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from sec_nlp.app.flows.artifacts import FlowArtifactStore
from sec_nlp.app.flows.compiled import CompiledStage
from sec_nlp.app.flows.contracts import ContractEvidenceBundle
from sec_nlp.app.flows.models import FlowDefaults, FlowSpec, FlowStageSpec
from sec_nlp.app.flows.runner import FlowRunner
from sec_nlp.pipelines.presets.analyze import AnalyzeConfig, AnalyzePipeline
from sec_nlp.pipelines.presets.analyze.models import AnalyzeResult
from sec_nlp.pipelines.presets.chat import ChatPipeline, ChatSettings
from sec_nlp.pipelines.presets.chat.models import ChatResult
from sec_nlp.pipelines.presets.exb import ExhibitConfig, ExhibitPipeline
from sec_nlp.pipelines.presets.exb.models import ExhibitResult
from sec_nlp.pipelines.presets.retrieve import (
    RetrievePipeline,
    RetrieveSettings,
)
from sec_nlp.pipelines.presets.retrieve.bridge import RetrieveChatSeedBundle
from sec_nlp.pipelines.presets.retrieve.models import RetrieveResult
from sec_nlp.pipelines.presets.warranty import WarrantyConfig, WarrantyPipeline
from sec_nlp.pipelines.presets.warranty.models import WarrantyResult


def _runner() -> FlowRunner:
    return FlowRunner(
        spec=FlowSpec(
            name="dispatch-smoke",
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


def test_run_stage_dispatches_supported_retrieve(monkeypatch) -> None:
    def _fake_retrieve_run(
        self: RetrievePipeline,
    ) -> tuple[RetrieveResult, RetrieveChatSeedBundle, list]:
        _ = self
        return (
            RetrieveResult(
                success=True,
                outputs=[Path("/tmp/retrieve_summary.json")],
                metadata={},
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
                chunks=[],
            ),
            [],
        )

    monkeypatch.setattr(
        RetrievePipeline,
        "run_for_flow_with_chunks",
        _fake_retrieve_run,
    )
    stage = CompiledStage(
        stage=FlowStageSpec(
            id="retrieve_seed",
            pipeline="retrieve",
            overrides={},
        ),
        settings=RetrieveSettings.model_validate(
            {
                "email": "test@example.com",
                "symbols": ["CDE"],
                "queries": ["liquidity risk"],
                "output_format": "json",
            }
        ),
    )
    result = _runner()._run_stage(stage, FlowArtifactStore())
    assert result.success is True


def test_run_stage_dispatches_supported_chat(monkeypatch) -> None:
    def _fake_chat_run(self: ChatPipeline) -> ChatResult:
        _ = self
        return ChatResult(
            success=True,
            outputs=[Path("/tmp/chat_summary.json")],
            metadata={},
            turns_processed=1,
            hits_retrieved=0,
            citations_returned=0,
            answer="answer",
            citation_ids=[],
        )

    monkeypatch.setattr(ChatPipeline, "run", _fake_chat_run)
    stage = CompiledStage(
        stage=FlowStageSpec(
            id="chat_answer",
            pipeline="chat",
            overrides={},
        ),
        settings=ChatSettings.model_validate(
            {
                "email": "test@example.com",
                "symbols": ["CDE"],
                "question": "What changed?",
                "interactive": False,
                "collections": ["retrieve"],
                "output_format": "json",
            }
        ),
    )
    result = _runner()._run_stage(stage, FlowArtifactStore())
    assert result.success is True


def test_run_stage_dispatches_supported_exhibit(monkeypatch) -> None:
    def _fake_exhibit_run(
        self: ExhibitPipeline,
    ) -> tuple[ExhibitResult, ContractEvidenceBundle]:
        _ = self
        return (
            ExhibitResult(
                success=True,
                outputs=[Path("/tmp/exhibit_summary.yaml")],
                metadata={},
            ),
            self._empty_contract_bundle(),
        )

    monkeypatch.setattr(ExhibitPipeline, "run_for_flow", _fake_exhibit_run)
    monkeypatch.setattr(ExhibitPipeline, "_build_components", lambda self: None)
    stage = CompiledStage(
        stage=FlowStageSpec(
            id="exhibit_seed",
            pipeline="exhibit",
            overrides={},
        ),
        settings=ExhibitConfig.model_validate(
            {
                "email": "test@example.com",
                "symbols": ["CDE"],
                "output_format": "json",
            }
        ),
    )
    result = _runner()._run_stage(stage, FlowArtifactStore())
    assert result.success is True


def test_run_stage_dispatches_supported_analyze(monkeypatch) -> None:
    def _fake_analyze_run(self: AnalyzePipeline) -> AnalyzeResult:
        _ = self
        return AnalyzeResult(
            success=True,
            outputs=[Path("/tmp/analyze_summary.json")],
            metadata={},
        )

    monkeypatch.setattr(AnalyzePipeline, "run", _fake_analyze_run)
    monkeypatch.setattr(AnalyzePipeline, "_build_components", lambda self: None)
    stage = CompiledStage(
        stage=FlowStageSpec(
            id="analyze_stage",
            pipeline="analyze",
            overrides={},
        ),
        settings=AnalyzeConfig.model_validate(
            {
                "email": "test@example.com",
                "symbols": ["CDE"],
                "search": {"queries": []},
                "vector_mode": "off",
            }
        ),
    )
    result = _runner()._run_stage(stage, FlowArtifactStore())
    assert result.success is True


def test_run_stage_dispatches_supported_warranty(monkeypatch) -> None:
    def _fake_warranty_run(self: WarrantyPipeline) -> WarrantyResult:
        _ = self
        return WarrantyResult(
            success=True,
            outputs=[Path("/tmp/warranty_summary.json")],
            metadata={},
        )

    monkeypatch.setattr(WarrantyPipeline, "run", _fake_warranty_run)
    monkeypatch.setattr(
        WarrantyPipeline, "_build_components", lambda self: None
    )
    stage = CompiledStage(
        stage=FlowStageSpec(
            id="warranty_stage",
            pipeline="warranty",
            overrides={},
        ),
        settings=WarrantyConfig.model_validate(
            {
                "email": "test@example.com",
                "symbols": ["CDE"],
            }
        ),
    )
    result = _runner()._run_stage(stage, FlowArtifactStore())
    assert result.success is True


def test_run_stage_rejects_unknown_pipeline() -> None:
    bad_stage = CompiledStage(
        stage=FlowStageSpec(
            id="bad_stage",
            pipeline="retrieve",
            overrides={},
        ),
        settings=RetrieveSettings.model_validate(
            {
                "email": "test@example.com",
                "symbols": ["CDE"],
                "queries": ["liquidity risk"],
                "output_format": "json",
            }
        ),
    )
    runner = _runner()
    bad_stage = CompiledStage(
        stage=bad_stage.stage.model_copy(update={"pipeline": "bad"}),
        settings=bad_stage.settings,
    )
    with pytest.raises(ValueError, match="Unsupported flow pipeline"):
        runner._run_stage(bad_stage, FlowArtifactStore())
