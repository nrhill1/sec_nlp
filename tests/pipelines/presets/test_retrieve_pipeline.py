"""Tests for retrieve pipeline and ranking helpers."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from langchain_core.documents import Document

from sec_nlp.core.edgar.efts_models import EFTSHit
from sec_nlp.pipelines.presets.retrieve import (
    RetrievePipeline,
    RetrieveSettings,
)
from sec_nlp.pipelines.presets.retrieve.models import RetrievalHit
from sec_nlp.pipelines.presets.retrieve.steps import (
    download_and_chunk_hits,
    rank_retrieval_hits,
)


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
        download_missing=False,
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


def test_download_and_chunk_hits_enriches_snippet_and_chunk_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = RetrieveSettings(
        email="test@example.com",
        symbols=["ABC"],
        queries=["supply chain"],
        sections=["1A"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        download_missing=False,
        snippet_chars=120,
    )
    html_path = (
        settings.dl_path
        / "sec-edgar-filings"
        / "ABC"
        / "10-K"
        / "0000123456-26-000100"
        / "doc.html"
    )
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text("<html><body>placeholder</body></html>")

    hit = RetrievalHit(
        symbol="ABC",
        query="supply chain disruption",
        accession_number="0000123456-26-000100",
        form_type="10-K",
        filed_date="2026-02-10",
        company_name="ABC Corp",
        cik="0000123456",
        score=0.91,
        edgar_url="https://example.com",
        snippet="original snippet",
    )

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.retrieve.steps.download_chunk._find_html_for_accession",
        lambda **kwargs: html_path,
    )

    captured: dict[str, object] = {}

    def _fake_transform_html(
        self,
        html_path: Path,
        *,
        section_filter=None,
        **kwargs,
    ) -> list[Document]:
        captured["section_filter"] = section_filter
        return [
            Document(
                page_content="General operations and governance update.",
                metadata={"section_number": "1", "chunk_index": 0},
            ),
            Document(
                page_content=(
                    "Supply chain disruption and vendor lead-time risk in core components."
                ),
                metadata={
                    "section_type": "item",
                    "section_number": "1A",
                    "chunk_index": 1,
                },
            ),
        ]

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.retrieve.steps.download_chunk.Loader.transform_html",
        _fake_transform_html,
    )

    enriched = download_and_chunk_hits(
        symbol="ABC",
        hits=[hit],
        settings=settings,
    )

    assert len(enriched) == 1
    assert enriched[0].snippet is not None
    assert "Supply chain disruption" in enriched[0].snippet
    assert enriched[0].section_type == "item"
    assert enriched[0].section_number == "1A"
    assert enriched[0].chunk_index == 1
    assert captured["section_filter"] is not None


def test_download_and_chunk_hits_preserves_efts_snippet_when_no_html(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = RetrieveSettings(
        email="test@example.com",
        symbols=["ABC"],
        queries=["warranty"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        download_missing=False,
    )
    hit = RetrievalHit(
        symbol="ABC",
        query="warranty accrual",
        accession_number="0000123456-26-000101",
        form_type="10-K",
        filed_date="2026-02-11",
        company_name="ABC Corp",
        cik="0000123456",
        score=0.73,
        edgar_url="https://example.com",
        snippet="efts snippet text",
    )

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.retrieve.steps.download_chunk._find_html_for_accession",
        lambda **kwargs: None,
    )

    enriched = download_and_chunk_hits(
        symbol="ABC",
        hits=[hit],
        settings=settings,
    )

    assert len(enriched) == 1
    assert enriched[0].snippet == "efts snippet text"
    assert enriched[0].section_number is None
    assert enriched[0].chunk_index is None
