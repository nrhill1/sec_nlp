"""Tests for retrieve pipeline and ranking helpers."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from langchain_core.documents import Document

from sec_nlp.core.edgar.efts_models import EFTSHit
from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.pipelines.presets.retrieve import (
    RetrievePipeline,
    RetrieveSettings,
)
from sec_nlp.pipelines.presets.retrieve.models import RetrievalHit
from sec_nlp.pipelines.presets.retrieve.steps import (
    candidate_search as candidate_search_steps,
    download_and_chunk_hits,
    download_chunk as download_chunk_steps,
    embed as embed_steps,
    index_retrieval_hits,
    prune_hits_by_query_terms,
    rank_retrieval_hits,
    rerank_with_embeddings,
)
from sec_nlp.types import JsonValue


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


def test_prune_hits_by_query_terms_filters_low_overlap_snippets() -> None:
    hits = [
        RetrievalHit(
            symbol="ABC",
            query="supply chain bottleneck",
            accession_number="0000123456-26-000001",
            form_type="10-K",
            filed_date="2026-02-01",
            company_name="ABC Corp",
            cik="0000123456",
            score=0.9,
            edgar_url="https://example.com/a",
            snippet="Supply chain bottleneck risk remains elevated.",
        ),
        RetrievalHit(
            symbol="ABC",
            query="supply chain bottleneck",
            accession_number="0000123456-26-000002",
            form_type="10-K",
            filed_date="2026-02-01",
            company_name="ABC Corp",
            cik="0000123456",
            score=0.8,
            edgar_url="https://example.com/b",
            snippet="Board compensation updates and governance details.",
        ),
    ]

    kept = prune_hits_by_query_terms(
        hits=hits,
        min_hits=1,
        min_ratio=0.25,
    )

    assert len(kept) == 1
    assert kept[0].accession_number == "0000123456-26-000001"


def test_embed_texts_with_cache_uses_sqlite_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = RetrieveSettings(
        email="test@example.com",
        symbols=["ABC"],
        queries=["supply chain"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        embedding_cache=True,
        embedding_cache_file=Path(".retrieve_embedding_cache.json"),
    )

    calls: list[list[str]] = []

    def _fake_batch_embed_documents(
        self,
        embedder,
        texts: list[str],
        show_progress: bool = False,
    ) -> list[list[float]]:
        calls.append(list(texts))
        return [[float(len(text))] for text in texts]

    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.batch_embed_documents",
        _fake_batch_embed_documents,
    )

    first = embed_steps.embed_texts_with_cache(
        texts=["alpha", "beta"],
        settings=settings,
        embedder=SimpleNamespace(),
        cache_prefix="snippet",
    )
    second = embed_steps.embed_texts_with_cache(
        texts=["beta", "alpha"],
        settings=settings,
        embedder=SimpleNamespace(),
        cache_prefix="snippet",
    )

    assert first == [[5.0], [4.0]]
    assert second == [[4.0], [5.0]]
    assert calls == [["alpha", "beta"]]
    assert settings.embedding_cache_path().with_suffix(".sqlite3").exists()


def test_embed_texts_with_cache_migrates_legacy_json_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = RetrieveSettings(
        email="test@example.com",
        symbols=["ABC"],
        queries=["supply chain"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        embedding_cache=True,
        embedding_cache_file=Path(".retrieve_embedding_cache.json"),
    )
    text = "legacy snippet"
    key = embed_steps._cache_key(
        model_name=settings.vdb.embedding_model,
        text=text,
        prefix="snippet",
    )
    legacy_path = settings.embedding_cache_path()
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        json.dumps({"version": 1, "entries": {key: [0.25, 0.75]}}),
        encoding="utf-8",
    )

    calls: list[list[str]] = []

    def _fake_batch_embed_documents(
        self,
        embedder,
        texts: list[str],
        show_progress: bool = False,
    ) -> list[list[float]]:
        calls.append(list(texts))
        return [[0.0]]

    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.batch_embed_documents",
        _fake_batch_embed_documents,
    )

    vectors = embed_steps.embed_texts_with_cache(
        texts=[text],
        settings=settings,
        embedder=SimpleNamespace(),
        cache_prefix="snippet",
    )

    assert vectors == [[0.25, 0.75]]
    assert calls == []

    db_path = settings.embedding_cache_path().with_suffix(".sqlite3")
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT vector_json FROM embeddings WHERE cache_key = ?",
            (key,),
        ).fetchone()
    assert row is not None


def test_mode_for_form_maps_6_k_to_current() -> None:
    assert (
        download_chunk_steps._mode_for_form(
            "6-K",
            fallback=FilingMode.annual,
        )
        == FilingMode.current
    )


def test_retrieve_settings_rejoins_comma_split_pipe_queries(
    tmp_path: Path,
) -> None:
    settings = RetrieveSettings(
        email="test@example.com",
        symbols=["ABC"],
        queries=[
            "Australian rare-earth supplier concentration and magnet-chain exposure||South China Sea shipping/security disruption risk to NdPr feedstock and REO flows||Export controls and tariff changes impacting REM pricing power",
            "margin risk",
            "and capex timing",
        ],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
    )

    assert settings.queries == [
        "Australian rare-earth supplier concentration and magnet-chain exposure",
        "South China Sea shipping/security disruption risk to NdPr feedstock and REO flows",
        "Export controls and tariff changes impacting REM pricing power, margin risk, and capex timing",
    ]


def test_retrieve_settings_keeps_explicit_query_list_without_pipes(
    tmp_path: Path,
) -> None:
    settings = RetrieveSettings(
        email="test@example.com",
        symbols=["ABC"],
        queries=["alpha query", "beta query"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
    )

    assert settings.queries == ["alpha query", "beta query"]


def test_candidate_search_filters_cross_symbol_hits() -> None:
    hits = [
        EFTSHit(
            accession_number="0001326801-26-000001",
            cik="0001326801",
            company_name="MP Materials Corp. (MP) (CIK 0001326801)",
            tickers=["MP"],
            form_type="10-K",
            filed_date=date(2026, 2, 1),
            score=9.1,
        ),
        EFTSHit(
            accession_number="0000915913-26-000018",
            cik="0000915913",
            company_name="ALBEMARLE CORP (ALB) (CIK 0000915913)",
            tickers=["ALB"],
            form_type="10-K",
            filed_date=date(2026, 2, 11),
            score=9.2,
        ),
    ]

    filtered = candidate_search_steps._filter_hits_for_symbol(
        hits=hits,
        symbol="MP",
        symbol_cik="0001326801",
    )

    assert len(filtered) == 1
    assert filtered[0].cik == "0001326801"


def test_candidate_search_keeps_hits_when_cik_matches_without_ticker() -> None:
    hits = [
        EFTSHit(
            accession_number="0001326801-26-000001",
            cik="0001326801",
            company_name="MP Materials Corp.",
            tickers=[],
            form_type="10-K",
            filed_date=date(2026, 2, 1),
            score=9.1,
        ),
        EFTSHit(
            accession_number="0000215466-24-000008",
            cik="0000215466",
            company_name="Coeur Mining, Inc. (CDE) (CIK 0000215466)",
            tickers=[],
            form_type="10-K",
            filed_date=date(2024, 2, 21),
            score=8.7,
        ),
    ]

    filtered = candidate_search_steps._filter_hits_for_symbol(
        hits=hits,
        symbol="MP",
        symbol_cik="0001326801",
    )

    assert len(filtered) == 1
    assert filtered[0].accession_number == "0001326801-26-000001"


def test_candidate_search_allows_unscoped_hits_when_symbol_missing() -> None:
    hits = [
        EFTSHit(
            accession_number="0001326801-26-000001",
            cik="0001326801",
            company_name="MP Materials Corp. (MP) (CIK 0001326801)",
            tickers=["MP"],
            form_type="10-K",
            filed_date=date(2026, 2, 1),
            score=9.1,
        ),
        EFTSHit(
            accession_number="0000215466-24-000008",
            cik="0000215466",
            company_name="Coeur Mining, Inc. (CDE) (CIK 0000215466)",
            tickers=["CDE"],
            form_type="10-K",
            filed_date=date(2024, 2, 21),
            score=8.7,
        ),
    ]

    filtered = candidate_search_steps._filter_hits_for_symbol(
        hits=hits,
        symbol="",
        symbol_cik=None,
    )

    assert len(filtered) == 2
    assert {hit.accession_number for hit in filtered} == {
        "0001326801-26-000001",
        "0000215466-24-000008",
    }


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


def test_retrieve_pipeline_runs_unscoped_without_symbols(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = RetrieveSettings(
        email="test@example.com",
        symbols=[],
        queries=["mine expansion"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        output_format="json",
        top_k=5,
        download_missing=False,
    )

    type _ObservedValue = list[str] | str | None
    observed: dict[str, _ObservedValue] = {}

    def _fake_candidate_search(
        *,
        symbol,
        queries,
        settings,
    ):
        observed["symbol"] = symbol
        observed["queries"] = list(queries)
        return {
            "mine expansion": [
                _efts_hit(
                    accession="0001801368-25-000009",
                    filed=date(2025, 2, 20),
                    score=0.93,
                    company="MP Materials Corp. (MP)",
                )
            ]
        }

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.retrieve.pipeline.run_candidate_search",
        _fake_candidate_search,
    )

    pipeline = RetrievePipeline(config=config)
    result = pipeline.run()

    assert result.success is True
    assert result.symbols_processed == 1
    assert result.queries_processed == 1
    assert result.hits_returned == 1
    assert observed["symbol"] is None
    assert observed["queries"] == ["mine expansion"]
    assert len(result.outputs) == 1
    assert "ALL" in str(result.outputs[0])


def test_retrieve_pipeline_respects_hydrate_top_n(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = RetrieveSettings(
        email="test@example.com",
        symbols=["ABC"],
        queries=["supply chain"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        output_format="json",
        top_k=3,
        hydrate_top_n=1,
        download_missing=False,
    )

    candidates = {
        "supply chain": [
            _efts_hit(
                accession="0000123456-26-000301",
                filed=date(2026, 2, 1),
                score=0.95,
                company="ABC Co",
            ),
            _efts_hit(
                accession="0000123456-26-000302",
                filed=date(2026, 2, 1),
                score=0.90,
                company="ABC Co",
            ),
            _efts_hit(
                accession="0000123456-26-000303",
                filed=date(2026, 2, 1),
                score=0.85,
                company="ABC Co",
            ),
        ]
    }

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.retrieve.pipeline.run_candidate_search",
        lambda symbol, queries, settings: candidates,
    )

    hydrated_batches: list[int] = []

    def _fake_download_and_chunk(symbol, hits, settings):
        hydrated_batches.append(len(hits))
        return hits

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.retrieve.pipeline.download_and_chunk_hits",
        _fake_download_and_chunk,
    )

    pipeline = RetrievePipeline(config=config)
    result = pipeline.run()

    assert result.success is True
    assert hydrated_batches == [1]

    json_path = next(path for path in result.outputs if path.suffix == ".json")
    payload = json.loads(json_path.read_text())
    symbol_meta = payload["metadata"]
    assert symbol_meta["hydrated_hits"] == 1
    assert symbol_meta["passthrough_hits"] == 2
    assert "stage_timings" in symbol_meta


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

    captured_section_filter = {"seen": False}

    def _fake_transform_html(
        self,
        html_path: Path,
        *,
        section_filter=None,
        **kwargs,
    ) -> list[Document]:
        captured_section_filter["seen"] = section_filter is not None
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
    assert captured_section_filter["seen"] is True


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


def test_rerank_with_embeddings_reorders_hits_with_fake_vectors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = RetrieveSettings(
        email="test@example.com",
        symbols=["ABC"],
        queries=["supply chain", "warranty"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        rerank_with_embeddings=True,
        embedding_weight=1.0,
    )
    hits = [
        RetrievalHit(
            symbol="ABC",
            query="supply chain",
            accession_number="0000123456-26-000110",
            form_type="10-K",
            filed_date="2026-02-12",
            company_name="ABC Corp",
            cik="0000123456",
            score=0.10,
            edgar_url="https://example.com/1",
            snippet="supply chain bottleneck risk",
        ),
        RetrievalHit(
            symbol="ABC",
            query="supply chain",
            accession_number="0000123456-26-000111",
            form_type="10-K",
            filed_date="2026-02-12",
            company_name="ABC Corp",
            cik="0000123456",
            score=0.90,
            edgar_url="https://example.com/2",
            snippet="executive compensation details",
        ),
    ]

    class _FakeEmbedder:
        def embed_query(self, query: str) -> list[float]:
            if "supply" in query:
                return [1.0, 0.0]
            return [0.0, 1.0]

    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.setup_embedding_model",
        lambda self: (_FakeEmbedder(), 2),
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.batch_embed_documents",
        lambda self, embedder, texts, show_progress=False: [
            [1.0, 0.0] if "supply" in text else [0.0, 1.0] for text in texts
        ],
    )

    reranked = rerank_with_embeddings(hits=hits, settings=settings)

    assert len(reranked) == 2
    assert reranked[0].accession_number == "0000123456-26-000110"
    assert reranked[0].score > reranked[1].score


def test_index_retrieval_hits_upserts_points_with_mock_client(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = RetrieveSettings(
        email="test@example.com",
        symbols=["ABC"],
        queries=["supply chain"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        index_results=True,
        dry_run=False,
    )
    hits = [
        RetrievalHit(
            symbol="ABC",
            query="supply chain",
            accession_number="0000123456-26-000120",
            form_type="10-K",
            filed_date="2026-02-13",
            company_name="ABC Corp",
            cik="0000123456",
            score=0.44,
            edgar_url="https://example.com/3",
            snippet="supply chain vendor concentration",
            section_type="item",
            section_number="1A",
            chunk_index=2,
        )
    ]

    class _FakeEmbedder:
        def embed_query(self, query: str) -> list[float]:
            return [1.0, 0.0]

    class _FakeQdrant:
        def __init__(self) -> None:
            self.created = False
            self.upserted_points = 0

        def collection_exists(self, collection_name: str) -> bool:
            return False

        def create_collection(self, **kwargs) -> None:
            self.created = True

        def upsert(self, *, collection_name: str, points, wait: bool) -> None:
            self.upserted_points = len(points)

    fake_client = _FakeQdrant()

    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.setup_embedding_model",
        lambda self: (_FakeEmbedder(), 2),
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.batch_embed_documents",
        lambda self, embedder, texts, show_progress=False: [[1.0, 0.0]],
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.setup_qdrant_client",
        lambda self: fake_client,
    )

    indexed = index_retrieval_hits(
        symbol="ABC",
        hits=hits,
        settings=settings,
    )

    assert indexed == hits
    assert fake_client.created is True
    assert fake_client.upserted_points == 1


def test_index_retrieval_hits_skips_existing_points_in_incremental_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = RetrieveSettings(
        email="test@example.com",
        symbols=["ABC"],
        queries=["supply chain"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        index_results=True,
        dry_run=False,
        incremental=True,
    )
    hits = [
        RetrievalHit(
            symbol="ABC",
            query="supply chain",
            accession_number="0000123456-26-000120",
            form_type="10-K",
            filed_date="2026-02-13",
            company_name="ABC Corp",
            cik="0000123456",
            score=0.44,
            edgar_url="https://example.com/3",
            snippet="supply chain vendor concentration",
            section_type="item",
            section_number="1A",
            chunk_index=2,
        ),
        RetrievalHit(
            symbol="ABC",
            query="supply chain",
            accession_number="0000123456-26-000121",
            form_type="10-K",
            filed_date="2026-02-13",
            company_name="ABC Corp",
            cik="0000123456",
            score=0.41,
            edgar_url="https://example.com/4",
            snippet="supply agreement terms",
            section_type="item",
            section_number="1A",
            chunk_index=3,
        ),
    ]

    class _FakeEmbedder:
        def embed_query(self, query: str) -> list[float]:
            return [1.0, 0.0]

    class _FakeQdrant:
        def __init__(self) -> None:
            self.upserted_points = 0
            self.retrieved_batches: list[list[str]] = []

        def collection_exists(self, collection_name: str) -> bool:
            return True

        def retrieve(
            self,
            *,
            collection_name: str,
            ids: list[str],
            with_payload: bool,
            with_vectors: bool,
        ) -> list[SimpleNamespace]:
            self.retrieved_batches.append(list(ids))
            return [SimpleNamespace(id=ids[0])]

        def upsert(self, *, collection_name: str, points, wait: bool) -> None:
            self.upserted_points = len(points)

    fake_client = _FakeQdrant()
    embedded_lengths: list[int] = []

    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.setup_embedding_model",
        lambda self: (_FakeEmbedder(), 2),
    )

    def _fake_batch_embed(
        self,
        embedder,
        texts: list[str],
        show_progress: bool = False,
    ) -> list[list[float]]:
        embedded_lengths.append(len(texts))
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.batch_embed_documents",
        _fake_batch_embed,
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.setup_qdrant_client",
        lambda self: fake_client,
    )

    indexed = index_retrieval_hits(
        symbol="ABC",
        hits=hits,
        settings=settings,
    )

    assert indexed == hits
    assert fake_client.retrieved_batches
    assert embedded_lengths == [1]
    assert fake_client.upserted_points == 1


def test_index_retrieval_hits_short_circuits_when_all_hits_exist(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = RetrieveSettings(
        email="test@example.com",
        symbols=["ABC"],
        queries=["supply chain"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        index_results=True,
        dry_run=False,
        incremental=True,
    )
    hits = [
        RetrievalHit(
            symbol="ABC",
            query="supply chain",
            accession_number="0000123456-26-000120",
            form_type="10-K",
            filed_date="2026-02-13",
            company_name="ABC Corp",
            cik="0000123456",
            score=0.44,
            edgar_url="https://example.com/3",
            snippet="supply chain vendor concentration",
            section_type="item",
            section_number="1A",
            chunk_index=2,
        )
    ]

    class _FakeQdrant:
        def __init__(self) -> None:
            self.upserted_points = 0

        def collection_exists(self, collection_name: str) -> bool:
            return True

        def retrieve(
            self,
            *,
            collection_name: str,
            ids: list[str],
            with_payload: bool,
            with_vectors: bool,
        ) -> list[SimpleNamespace]:
            return [SimpleNamespace(id=id_) for id_ in ids]

        def upsert(self, *, collection_name: str, points, wait: bool) -> None:
            self.upserted_points = len(points)

    fake_client = _FakeQdrant()
    embedder_called = {"value": False}

    def _fake_setup_embedding_model(self):
        embedder_called["value"] = True
        return SimpleNamespace(), 2

    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.setup_embedding_model",
        _fake_setup_embedding_model,
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.setup_qdrant_client",
        lambda self: fake_client,
    )

    indexed = index_retrieval_hits(
        symbol="ABC",
        hits=hits,
        settings=settings,
    )

    assert indexed == hits
    assert embedder_called["value"] is False
    assert fake_client.upserted_points == 0


def test_retrieve_pipeline_reuses_vector_components_across_symbols(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = RetrieveSettings(
        email="test@example.com",
        symbols=["BHP", "RIO"],
        queries=["supply chain"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        output_format="json",
        top_k=5,
        download_missing=False,
        rerank_with_embeddings=True,
        index_results=True,
    )

    candidates = {
        "supply chain": [
            _efts_hit(
                accession="0000123456-26-000201",
                filed=date(2026, 2, 1),
                score=0.91,
                company="Sample Corp",
            )
        ]
    }

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.retrieve.pipeline.run_candidate_search",
        lambda symbol, queries, settings: candidates,
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.retrieve.pipeline.download_and_chunk_hits",
        lambda symbol, hits, settings: hits,
    )

    setup_calls = {"embedder": 0, "qdrant": 0}
    fake_embedder = SimpleNamespace()
    fake_qdrant = SimpleNamespace()

    def _fake_setup_embedder(self):
        setup_calls["embedder"] += 1
        return fake_embedder, 2

    def _fake_setup_qdrant(self):
        setup_calls["qdrant"] += 1
        return fake_qdrant

    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.setup_embedding_model",
        _fake_setup_embedder,
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.setup_qdrant_client",
        _fake_setup_qdrant,
    )

    rerank_embedder_args: list[SimpleNamespace | None] = []
    index_embedder_args: list[SimpleNamespace | None] = []
    index_qdrant_args: list[SimpleNamespace | None] = []

    def _fake_rerank(
        *, hits, settings, embedder=None, allow_setup_fallback=True
    ):
        rerank_embedder_args.append(embedder)
        return hits

    def _fake_index(
        *,
        symbol,
        hits,
        settings,
        qdrant_client=None,
        embedder=None,
        embedding_dim=None,
        market_signals=None,
        allow_setup_fallback=True,
    ):
        index_qdrant_args.append(qdrant_client)
        index_embedder_args.append(embedder)
        return hits

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.retrieve.pipeline.rerank_with_embeddings",
        _fake_rerank,
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.retrieve.pipeline.index_retrieval_hits",
        _fake_index,
    )

    pipeline = RetrievePipeline(config=config)
    result = pipeline.run()

    assert result.success is True
    assert setup_calls["embedder"] == 1
    assert setup_calls["qdrant"] == 1
    assert rerank_embedder_args == [fake_embedder, fake_embedder]
    assert index_embedder_args == [fake_embedder, fake_embedder]
    assert index_qdrant_args == [fake_qdrant, fake_qdrant]


def test_retrieve_pipeline_limits_failed_vector_setup_retries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = RetrieveSettings(
        email="test@example.com",
        symbols=["BHP", "RIO"],
        queries=["supply chain"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        output_format="json",
        top_k=5,
        download_missing=False,
        rerank_with_embeddings=True,
        index_results=True,
    )

    candidates = {
        "supply chain": [
            _efts_hit(
                accession="0000123456-26-000202",
                filed=date(2026, 2, 2),
                score=0.9,
                company="Sample Corp",
            )
        ]
    }

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.retrieve.pipeline.run_candidate_search",
        lambda symbol, queries, settings: candidates,
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.retrieve.pipeline.download_and_chunk_hits",
        lambda symbol, hits, settings: hits,
    )

    setup_calls = {"embedder": 0, "qdrant": 0}

    def _failing_setup_embedder(self):
        setup_calls["embedder"] += 1
        raise RuntimeError("embedder unavailable")

    def _failing_setup_qdrant(self):
        setup_calls["qdrant"] += 1
        raise RuntimeError("qdrant unavailable")

    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.setup_embedding_model",
        _failing_setup_embedder,
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.setup_qdrant_client",
        _failing_setup_qdrant,
    )

    pipeline = RetrievePipeline(config=config)
    result = pipeline.run()

    assert result.success is True
    # One prewarm attempt in _build_components + one runtime retry.
    assert setup_calls["embedder"] == 2
    assert setup_calls["qdrant"] == 2


def test_retrieve_pipeline_adds_market_context_to_output_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = RetrieveSettings(
        email="test@example.com",
        symbols=["ABC"],
        queries=["supply chain"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        output_format="json",
        top_k=5,
        download_missing=False,
        include_market_signals=True,
    )
    candidates = {
        "supply chain": [
            _efts_hit(
                accession="0000123456-26-000010",
                filed=date(2026, 2, 2),
                score=0.88,
                company="ABC Co",
            )
        ]
    }

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.retrieve.pipeline.run_candidate_search",
        lambda symbol, queries, settings: candidates,
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.retrieve.pipeline.build_market_context",
        lambda **kwargs: SimpleNamespace(
            model_dump=lambda mode="json", exclude_none=True: {
                "window": "2024-01-01..2024-12-31",
                "benchmark": "SPY",
                "symbols": ["ABC"],
                "metrics": [
                    {
                        "symbol": "ABC",
                        "return_pct": 1.0,
                        "benchmark_return_pct": 0.5,
                        "spread_pct": 0.5,
                        "beta": 1.1,
                    }
                ],
            }
        ),
    )

    pipeline = RetrievePipeline(config=config)
    result = pipeline.run()

    assert result.success is True
    json_path = next(path for path in result.outputs if path.suffix == ".json")
    payload = json.loads(json_path.read_text())
    market_context = payload["metadata"].get("market_context")
    assert isinstance(market_context, dict)
    assert market_context["benchmark"] == "SPY"
    assert market_context["metrics"][0]["symbol"] == "ABC"


def test_index_retrieval_hits_includes_market_signals_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = RetrieveSettings(
        email="test@example.com",
        symbols=["ABC"],
        queries=["supply chain"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        index_results=True,
        include_market_signals=True,
        dry_run=False,
    )
    hits = [
        RetrievalHit(
            symbol="ABC",
            query="supply chain",
            accession_number="0000123456-26-000130",
            form_type="10-K",
            filed_date="2026-02-14",
            company_name="ABC Corp",
            cik="0000123456",
            score=0.9,
            edgar_url="https://example.com/5",
            snippet="sample snippet",
        )
    ]

    class _FakeEmbedder:
        pass

    captured_payloads: list[dict[str, JsonValue]] = []

    class _FakeQdrant:
        def collection_exists(self, collection_name: str) -> bool:
            return False

        def create_collection(self, **kwargs) -> None:
            return None

        def upsert(self, *, collection_name: str, points, wait: bool) -> None:
            for point in points:
                captured_payloads.append(point.payload)

    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.setup_embedding_model",
        lambda self: (_FakeEmbedder(), 2),
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.batch_embed_documents",
        lambda self, embedder, texts, show_progress=False: [[1.0, 0.0]],
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.vector.config.VectorConfig.setup_qdrant_client",
        lambda self: _FakeQdrant(),
    )

    index_retrieval_hits(
        symbol="ABC",
        hits=hits,
        settings=settings,
        market_signals={
            "window": "2024-01-01..2024-12-31",
            "benchmark": "SPY",
            "symbol": "ABC",
            "spread_pct": 0.5,
        },
    )

    assert len(captured_payloads) == 1
    market_signals = captured_payloads[0].get("market_signals")
    assert isinstance(market_signals, dict)
    benchmark = None
    for key, value in market_signals.items():
        if key == "benchmark" and isinstance(value, str):
            benchmark = value
            break
    assert benchmark == "SPY"
