"""Tests for retrieve pipeline and ranking helpers."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from langchain_core.documents import Document

from sec_nlp.core.edgar.efts_models import EFTSHit
from sec_nlp.pipelines.presets.retrieve import (
    RetrievePipeline,
    RetrieveSettings,
)
from sec_nlp.pipelines.presets.retrieve.models import RetrievalHit
from sec_nlp.pipelines.presets.retrieve.steps import (
    download_and_chunk_hits,
    index_retrieval_hits,
    rank_retrieval_hits,
    rerank_with_embeddings,
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
        return object(), 2

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
