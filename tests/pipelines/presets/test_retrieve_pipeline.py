"""Tests for retrieve pipeline and ranking helpers."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sec_nlp.core.edgar.efts_models import EFTSHit
from sec_nlp.pipelines.presets.retrieve import (
    RetrievePipeline,
    RetrieveSettings,
)
from sec_nlp.pipelines.presets.retrieve.steps import rank_retrieval_hits


def _efts_hit(
    *,
    accession: str,
    filed: date,
    score: float,
    company: str = "Sample Corp",
) -> EFTSHit:
    return EFTSHit(
        accession_number=accession,
        cik="0000123456",
        company_name=company,
        tickers=["ABC"],
        form_type="10-K",
        filed_date=filed,
        snippet="sample snippet",
        score=score,
    )


def test_rank_retrieval_hits_sorts_and_dedupes() -> None:
    ranked = rank_retrieval_hits(
        symbol="ABC",
        candidates_by_query={
            "supply chain": [
                _efts_hit(
                    accession="0000123456-26-000001",
                    filed=date(2026, 2, 1),
                    score=0.9,
                ),
                _efts_hit(
                    accession="0000123456-26-000001",
                    filed=date(2026, 2, 1),
                    score=0.7,
                ),
            ],
            "warranty": [
                _efts_hit(
                    accession="0000123456-26-000002",
                    filed=date(2026, 2, 2),
                    score=0.8,
                )
            ],
        },
        top_k=10,
    )

    assert len(ranked) == 2
    assert ranked[0].score == 0.9
    assert ranked[0].accession_number == "0000123456-26-000001"


def test_retrieve_pipeline_run_writes_outputs_with_mocked_search(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = RetrieveSettings(
        email="test@example.com",
        symbols=["ABC"],
        queries=["supply chain", "warranty"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        output_format="all",
        top_k=5,
    )

    candidates = {
        "supply chain": [
            _efts_hit(
                accession="0000123456-26-000003",
                filed=date(2026, 2, 3),
                score=0.88,
                company="ABC Co",
            )
        ],
        "warranty": [
            _efts_hit(
                accession="0000123456-26-000004",
                filed=date(2026, 2, 4),
                score=0.75,
                company="ABC Co",
            )
        ],
    }

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.retrieve.pipeline.run_candidate_search",
        lambda symbol, queries, settings: candidates,
    )

    pipeline = RetrievePipeline(config=config)
    result = pipeline.run()

    assert result.success is True
    assert result.symbols_processed == 1
    assert result.queries_processed == 2
    assert result.hits_returned == 2
    assert len(result.outputs) == 3

    json_path = next(path for path in result.outputs if path.suffix == ".json")
    payload = json.loads(json_path.read_text())
    expected_short_id = config.short_id if config.short_id > 0 else None
    assert payload["run_id"] == str(config.run_id)
    assert payload["run_short_id"] == expected_short_id
    assert payload["queries"] == ["supply chain", "warranty"]

    csv_path = next(path for path in result.outputs if path.suffix == ".csv")
    lines = csv_path.read_text().splitlines()
    assert lines[0].startswith("# run_timestamp:")
    assert lines[1].startswith("# run_short_id:")
    assert lines[2].startswith("# run_id:")
    assert lines[3].startswith("# run_short_id_display:")
    assert lines[4].startswith("symbol,query")
