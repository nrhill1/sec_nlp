# tests/pipelines/presets/test_exhibit_candidates.py
"""Tests for EXB candidate-first accession narrowing."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from sec_nlp.core.edgar.efts_models import EFTSHit
from sec_nlp.pipelines.presets.exb.config import ExhibitConfig
from sec_nlp.pipelines.presets.exb.steps import candidates as candidate_steps
from sec_nlp.pipelines.presets.retrieve.config import RetrieveSettings
from sec_nlp.pipelines.vector import VectorConfig


def _config(tmp_path: Path, **updates: object) -> ExhibitConfig:
    base = ExhibitConfig(
        email="test@example.com",
        symbols=["CAT"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        dry_run=True,
        vdb=VectorConfig(embedding_model="granite-embedding:30m"),
    )
    payload = base.model_dump(mode="python")
    payload.update(updates)
    return ExhibitConfig.model_validate(payload)


def test_candidate_queries_fallback_uses_search_terms(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        candidate_queries=[],
        search_terms=[" master supply agreement ", "MASTER SUPPLY AGREEMENT"],
        candidate_query_cap=4,
    )

    queries = candidate_steps.candidate_queries_for_exhibit(config)

    assert queries
    assert queries[0] == "master supply agreement"
    assert len(queries) <= 4


def test_build_candidate_accessions_uses_retrieve_ranking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(
        tmp_path,
        candidate_queries=["exclusive supply agreement"],
        candidate_top_k=25,
        efts_candidates=150,
        candidate_query_term_min_hits=0,
        candidate_query_term_min_ratio=0.0,
    )

    hit = EFTSHit(
        accession_number="0001234567-26-000001",
        cik="0001234567",
        company_name="Example Mining Corp",
        tickers=["CAT"],
        form_type="10-K",
        filed_date=date(2026, 1, 10),
        snippet="Exclusive supply agreement with pricing and terms",
        score=0.91,
    )

    def _fake_run_candidate_search(
        *,
        symbol: str | None,
        queries: list[str],
        settings: RetrieveSettings,
    ) -> dict[str, list[EFTSHit]]:
        assert symbol == "CAT"
        assert settings.efts_candidates == 150
        assert settings.top_k == 25
        assert settings.forms == ["10-K"]
        return {queries[0]: [hit]}

    monkeypatch.setattr(
        candidate_steps,
        "run_candidate_search",
        _fake_run_candidate_search,
    )

    accessions = candidate_steps.build_candidate_accessions(
        symbol="CAT",
        config=config,
    )

    assert accessions == {"0001234567-26-000001"}
