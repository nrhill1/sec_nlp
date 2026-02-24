# tests/pipelines/presets/test_chat_pipeline.py
"""Tests for RAG chat pipeline."""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from sec_nlp.pipelines.presets.chat import (
    ChatPipeline,
    ChatSeedBundle,
    ChatSeedChunk,
    ChatSettings,
)
from sec_nlp.pipelines.presets.chat.pipeline import _RetrievedChunk
from sec_nlp.pipelines.vector.config import VectorConfig
from sec_nlp.types import JsonValue


def test_chat_pipeline_run_writes_outputs_with_mocked_retrieval(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["CDE"],
        question="What changed in liquidity risk?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        output_format="all",
        collections=["retrieve", "analyze"],
        forms=["10-K"],
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        top_k=5,
    )

    monkeypatch.setattr(
        ChatPipeline,
        "_search_collections",
        lambda self, question, **_: [
            _RetrievedChunk(
                collection="retrieve",
                score=0.91,
                symbol="CDE",
                accession_number="0000215466-24-000003",
                form_type="10-K",
                filed_date="2024-02-21",
                source="https://www.sec.gov/ixviewer/ix.html",
                snippet="Liquidity risk increased due to higher debt servicing costs.",
            )
        ],
    )
    monkeypatch.setattr(
        ChatPipeline,
        "_build_answer",
        lambda self, question, citations, external_context="": (
            "Liquidity risk increased, primarily from debt costs. [C1]",
            ["C1"],
        ),
    )

    result = ChatPipeline(config=config).run()

    assert result.success is True
    assert result.hits_retrieved == 1
    assert result.citations_returned == 1
    assert result.citation_ids == ["C1"]
    assert len(result.outputs) == 3

    json_path = next(path for path in result.outputs if path.suffix == ".json")
    payload = json.loads(json_path.read_text())
    expected_short_id = config.short_id if config.short_id > 0 else None
    assert payload["run_id"] == str(config.run_id)
    assert payload["run_short_id"] == expected_short_id
    assert payload["question"] == "What changed in liquidity risk?"
    assert payload["citation_ids"] == ["C1"]
    assert payload["metadata"]["forms_filter"] == ["10-K"]
    assert payload["metadata"]["filed_after"] == "2024-01-01"
    assert payload["metadata"]["filed_before"] == "2024-12-31"

    csv_path = next(path for path in result.outputs if path.suffix == ".csv")
    lines = csv_path.read_text().splitlines()
    assert lines[0].startswith("# run_timestamp:")
    assert lines[1].startswith("# run_short_id:")
    assert lines[2].startswith("# run_id:")
    assert lines[3].startswith("# run_short_id_display:")
    assert lines[4] == "turn_index,role,message,citations"


def test_chat_pipeline_multi_symbol_outputs_use_multi_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["CDE", "FCX"],
        question="What changed in liquidity risk?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        output_format="json",
        collections=["retrieve"],
        forms=["10-K"],
        top_k=5,
    )

    monkeypatch.setattr(
        ChatPipeline,
        "_search_collections",
        lambda self, question, **_: [
            _RetrievedChunk(
                collection="retrieve",
                score=0.91,
                symbol="CDE",
                accession_number="0000215466-24-000003",
                form_type="10-K",
                filed_date="2024-02-21",
                source="https://www.sec.gov/ixviewer/ix.html",
                snippet="Liquidity risk increased due to higher debt servicing costs.",
            )
        ],
    )
    monkeypatch.setattr(
        ChatPipeline,
        "_build_answer",
        lambda self, question, citations, external_context="": (
            "Liquidity risk increased. [C1]",
            ["C1"],
        ),
    )

    result = ChatPipeline(config=config).run()

    assert result.success is True
    json_path = next(path for path in result.outputs if path.suffix == ".json")
    assert "/chat/MULTI/" in str(json_path)
    payload = json.loads(json_path.read_text())
    assert payload["symbol"] == "MULTI"
    assert payload["metadata"]["output_scope_symbol"] == "MULTI"


def test_chat_pipeline_uses_seed_context_without_collection_search(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["CDE"],
        question="What changed in liquidity risk?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        output_format="json",
        collections=["retrieve"],
        forms=["10-K"],
        seed_context=ChatSeedBundle(
            upstream_pipeline="retrieve",
            upstream_run_id="00000000-0000-0000-0000-000000000123",
            upstream_short_id=123,
            symbols=["CDE"],
            queries=["liquidity risk"],
            chunks=[
                ChatSeedChunk(
                    collection="retrieve",
                    score=0.91,
                    symbol="CDE",
                    accession_number="0000215466-24-000003",
                    form_type="10-K",
                    filed_date="2024-02-21",
                    source="https://www.sec.gov/ixviewer/ix.html",
                    snippet=(
                        "Liquidity risk increased due to higher debt servicing "
                        "costs."
                    ),
                )
            ],
        ),
    )

    monkeypatch.setattr(
        ChatPipeline,
        "_search_collections",
        lambda self, question, **_: pytest.fail(
            "seeded context path should bypass collection search"
        ),
    )
    monkeypatch.setattr(
        ChatPipeline,
        "_build_answer",
        lambda self, question, citations, external_context="": (
            "Liquidity risk increased, primarily from debt costs. [C1]",
            ["C1"],
        ),
    )

    result = ChatPipeline(config=config).run()

    assert result.success is True
    assert result.hits_retrieved == 1
    assert result.citations_returned == 1
    assert result.metadata.get("seeded_context") is True
    assert result.metadata.get("seeded_context_source") == "retrieve"


def test_chat_pipeline_falls_back_to_collection_search_when_seed_empty(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["CDE"],
        question="What changed in liquidity risk?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        output_format="json",
        collections=["retrieve"],
        forms=["10-K"],
        seed_context=ChatSeedBundle(
            upstream_pipeline="retrieve",
            upstream_run_id="00000000-0000-0000-0000-000000000123",
            upstream_short_id=123,
            symbols=["CDE"],
            queries=["liquidity risk"],
            chunks=[],
        ),
    )

    calls = {"search": 0}

    def _fake_search_collections(self, question: str, **kwargs):
        _ = question, kwargs
        calls["search"] += 1
        return [
            _RetrievedChunk(
                collection="retrieve",
                score=0.87,
                symbol="CDE",
                accession_number="0000215466-24-000003",
                form_type="10-K",
                filed_date="2024-02-21",
                source="https://www.sec.gov/ixviewer/ix.html",
                snippet="Liquidity risk increased due to higher debt servicing costs.",
            )
        ]

    monkeypatch.setattr(
        ChatPipeline,
        "_search_collections",
        _fake_search_collections,
    )
    monkeypatch.setattr(
        ChatPipeline,
        "_build_answer",
        lambda self, question, citations, external_context="": (
            "Liquidity risk increased, primarily from debt costs. [C1]",
            ["C1"],
        ),
    )

    result = ChatPipeline(config=config).run()

    assert result.success is True
    assert result.hits_retrieved == 1
    assert calls["search"] == 1
    assert result.metadata.get("seeded_context") is True
    assert (
        result.metadata.get("seeded_context_fallback_to_vector_search") is True
    )


def test_chunk_matches_filters_by_form_and_date() -> None:
    chunk = _RetrievedChunk(
        collection="retrieve",
        score=0.9,
        symbol="NAMM",
        accession_number="0000000000-24-000001",
        form_type="6-K/A",
        filed_date="2024-05-10",
        source="https://example.com",
        snippet="sample",
    )

    assert ChatPipeline._chunk_matches_filters(
        chunk,
        forms={"6-K"},
        filed_after=None,
        filed_before=None,
    )
    assert not ChatPipeline._chunk_matches_filters(
        chunk,
        forms={"8-K"},
        filed_after=None,
        filed_before=None,
    )
    assert ChatPipeline._chunk_matches_filters(
        chunk,
        forms={"6-K"},
        filed_after=date(2024, 1, 1),
        filed_before=date(2024, 12, 31),
    )
    assert not ChatPipeline._chunk_matches_filters(
        chunk,
        forms={"6-K"},
        filed_after=date(2024, 6, 1),
        filed_before=None,
    )


def test_search_collections_applies_form_and_date_filters(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["NAMM"],
        question="What changed?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        collections=["retrieve"],
        forms=["6-K"],
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        top_k=3,
    )

    class _FakeEmbedder:
        def embed_query(self, query: str) -> list[float]:
            return [0.1, 0.2]

    class _FakePoint:
        def __init__(self, payload: dict[str, JsonValue], score: float) -> None:
            self.payload = payload
            self.score = score

    class _FakeResponse:
        def __init__(self, points: list[_FakePoint]) -> None:
            self.points = points

    class _FakeQdrant:
        def __init__(self) -> None:
            self.last_limit: int | None = None

        def collection_exists(self, name: str) -> bool:
            return True

        def query_points(self, **kwargs):
            self.last_limit = int(kwargs["limit"])
            return _FakeResponse(
                [
                    _FakePoint(
                        payload={
                            "symbol": "NAMM",
                            "form_type": "6-K",
                            "filed_date": "2024-06-01",
                            "snippet": "kept chunk",
                        },
                        score=0.95,
                    ),
                    _FakePoint(
                        payload={
                            "symbol": "NAMM",
                            "form_type": "8-K",
                            "filed_date": "2024-06-01",
                            "snippet": "wrong form",
                        },
                        score=0.94,
                    ),
                    _FakePoint(
                        payload={
                            "symbol": "NAMM",
                            "form_type": "6-K",
                            "filed_date": "2023-12-31",
                            "snippet": "too old",
                        },
                        score=0.93,
                    ),
                ]
            )

    fake_qdrant = _FakeQdrant()

    monkeypatch.setattr(
        VectorConfig,
        "setup_embedding_model",
        lambda self: (_FakeEmbedder(), 2),
    )
    monkeypatch.setattr(
        VectorConfig,
        "setup_qdrant_client",
        lambda self: fake_qdrant,
    )

    chunks = ChatPipeline(config=config)._search_collections("neodymium")

    assert len(chunks) == 1
    assert chunks[0].form_type == "6-K"
    assert chunks[0].snippet == "kept chunk"
    assert fake_qdrant.last_limit == 32


def test_search_collections_prefetches_missing_collection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["NAMM"],
        question="What changed?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        collections=["retrieve_6k_namm"],
        forms=["6-K"],
        prefetch_retrieve=True,
        top_k=2,
    )

    class _FakeEmbedder:
        def embed_query(self, query: str) -> list[float]:
            return [0.2, 0.1]

    class _FakePoint:
        def __init__(self, payload: dict[str, JsonValue], score: float) -> None:
            self.payload = payload
            self.score = score

    class _FakeResponse:
        def __init__(self, points: list[_FakePoint]) -> None:
            self.points = points

    class _FakeCollectionInfo:
        def __init__(self, points_count: int) -> None:
            self.points_count = points_count

    class _FakeQdrant:
        def __init__(self) -> None:
            self.exists = False

        def collection_exists(self, name: str) -> bool:
            return self.exists

        def get_collection(self, name: str):
            return _FakeCollectionInfo(points_count=5 if self.exists else 0)

        def query_points(self, **kwargs):
            return _FakeResponse(
                [
                    _FakePoint(
                        payload={
                            "symbol": "NAMM",
                            "form_type": "6-K",
                            "filed_date": "2024-06-01",
                            "snippet": "hydrated chunk",
                        },
                        score=0.8,
                    )
                ]
            )

    fake_qdrant = _FakeQdrant()
    hydrated: dict[str, bool] = {"called": False}

    monkeypatch.setattr(
        VectorConfig,
        "setup_embedding_model",
        lambda self: (_FakeEmbedder(), 2),
    )
    monkeypatch.setattr(
        VectorConfig,
        "setup_qdrant_client",
        lambda self: fake_qdrant,
    )
    monkeypatch.setattr(
        ChatPipeline,
        "_hydrate_retrieve_collection",
        lambda self, collection, symbols, question: hydrated.update(
            {"called": True}
        )
        or setattr(fake_qdrant, "exists", True)
        or True,
    )

    chunks = ChatPipeline(config=config)._search_collections("neodymium")

    assert hydrated["called"] is True
    assert len(chunks) == 1
    assert chunks[0].snippet == "hydrated chunk"


def test_hydrate_retrieve_collection_uses_serializable_vdb_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["MP"],
        question="What changed?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        collections=["retrieve"],
        prefetch_retrieve=True,
        prefetch_queries=["rare earth"],
        prefetch_top_k=5,
        prefetch_efts_candidates=20,
        vdb=VectorConfig(qdrant_location=".qdrant/rems"),
    )
    pipeline = ChatPipeline(config=config)

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.chat.pipeline.RetrievePipeline.run",
        lambda self: SimpleNamespace(success=True),
    )

    hydrated = pipeline._hydrate_retrieve_collection(
        collection="retrieve",
        symbols=["MP"],
        question="what changed",
    )

    assert hydrated is True


def test_rerank_chunks_mmr_prefers_diversity(tmp_path: Path) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["NAMM"],
        question="What changed?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        rerank_mode="mmr",
        rerank_lambda=0.25,
        rerank_candidates=4,
        top_k=2,
    )
    chunks = [
        _RetrievedChunk(
            collection="retrieve",
            score=0.95,
            symbol="NAMM",
            accession_number="A1",
            form_type="6-K",
            filed_date="2024-06-01",
            source=None,
            snippet="chunk a",
        ),
        _RetrievedChunk(
            collection="retrieve",
            score=0.94,
            symbol="NAMM",
            accession_number="A2",
            form_type="6-K",
            filed_date="2024-06-01",
            source=None,
            snippet="chunk b",
        ),
        _RetrievedChunk(
            collection="retrieve",
            score=0.90,
            symbol="NAMM",
            accession_number="A3",
            form_type="6-K",
            filed_date="2024-06-01",
            source=None,
            snippet="chunk c",
        ),
    ]

    class _FakeEmbedder:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [
                [1.0, 0.0],  # chunk a (most relevant)
                [0.99, 0.01],  # chunk b (near-duplicate)
                [0.6, 0.8],  # chunk c (diverse)
            ]

    reranked = ChatPipeline(config=config)._rerank_chunks_mmr(
        chunks=chunks,
        query_vector=[1.0, 0.0],
        embedder=_FakeEmbedder(),
    )

    assert reranked[0].snippet == "chunk a"
    assert reranked[1].snippet == "chunk c"


def test_rerank_chunks_mmr_uses_stored_vectors_without_reembedding(
    tmp_path: Path,
) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["NAMM"],
        question="What changed?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        rerank_mode="mmr",
        rerank_lambda=0.25,
        rerank_candidates=4,
        top_k=2,
    )
    chunks = [
        _RetrievedChunk(
            collection="retrieve",
            score=0.95,
            symbol="NAMM",
            accession_number="A1",
            form_type="6-K",
            filed_date="2024-06-01",
            source=None,
            snippet="chunk a",
            vector=[1.0, 0.0],
        ),
        _RetrievedChunk(
            collection="retrieve",
            score=0.94,
            symbol="NAMM",
            accession_number="A2",
            form_type="6-K",
            filed_date="2024-06-01",
            source=None,
            snippet="chunk b",
            vector=[0.99, 0.01],
        ),
        _RetrievedChunk(
            collection="retrieve",
            score=0.90,
            symbol="NAMM",
            accession_number="A3",
            form_type="6-K",
            filed_date="2024-06-01",
            source=None,
            snippet="chunk c",
            vector=[0.6, 0.8],
        ),
    ]

    class _FailEmbedder:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            raise AssertionError("embed_documents should not be called")

    reranked = ChatPipeline(config=config)._rerank_chunks_mmr(
        chunks=chunks,
        query_vector=[1.0, 0.0],
        embedder=_FailEmbedder(),
    )

    assert reranked[0].snippet == "chunk a"
    assert reranked[1].snippet == "chunk c"


def test_build_external_context_uses_market_and_news(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["NAMM"],
        question="How do geopolitics affect neodymium pricing?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        include_market_context=True,
        include_news_context=True,
    )
    pipeline = ChatPipeline(config=config)

    monkeypatch.setattr(
        ChatPipeline,
        "_market_context_lines",
        lambda self, symbols: (
            ["- market line"],
            symbols,
            {
                "window": "2024-01-01..2024-01-31",
                "benchmark": "SPY",
                "symbols": list(symbols),
                "metrics": [],
            },
        ),
    )
    monkeypatch.setattr(
        ChatPipeline,
        "_news_context_lines",
        lambda self, symbol, question: ["- news line"],
    )

    context_text, context_meta = pipeline._build_external_context(
        question="How do geopolitics affect neodymium pricing?",
        citations=[],
    )

    assert "Market context" in context_text
    assert "News/geopolitics context" in context_text
    assert context_meta["market_context_items"] == 1
    assert context_meta["news_context_items"] == 1
    assert context_meta["market_context_profile"] == "standard"


def test_build_external_context_skips_multi_symbol_scope(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["AEM", "AREC"],
        question="How do geopolitics affect neodymium pricing?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        include_market_context=True,
        include_news_context=True,
    )
    pipeline = ChatPipeline(config=config)

    monkeypatch.setattr(
        ChatPipeline,
        "_market_context_lines",
        lambda self, symbols: (_ for _ in ()).throw(
            AssertionError("_market_context_lines should not be called")
        ),
    )
    monkeypatch.setattr(
        ChatPipeline,
        "_news_context_lines",
        lambda self, symbol, question: (_ for _ in ()).throw(
            AssertionError("_news_context_lines should not be called")
        ),
    )
    context_text, context_meta = pipeline._build_external_context(
        question="How do geopolitics affect neodymium pricing?",
        citations=[],
    )

    assert context_text == ""
    assert context_meta["market_context_items"] == 0
    assert context_meta["news_context_items"] == 0
    assert (
        context_meta["market_context_skipped"]
        == "no_retrieved_symbols_for_multi_scope"
    )
    assert context_meta["news_context_skipped"] == "multiple_symbols"
    assert context_meta["symbol_scope"] == ["AEM", "AREC"]


def test_build_external_context_uses_multi_symbol_market_lines(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["AEM", "AREC"],
        question="How do geopolitics affect neodymium pricing?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        include_market_context=True,
        include_news_context=False,
    )
    pipeline = ChatPipeline(config=config)
    chunks = [
        _RetrievedChunk(
            collection="retrieve",
            score=0.9,
            symbol="AEM",
            accession_number="A1",
            form_type="10-K",
            filed_date="2024-12-31",
            source=None,
            snippet="AEM filing snippet.",
        ),
        _RetrievedChunk(
            collection="retrieve",
            score=0.89,
            symbol="AREC",
            accession_number="B1",
            form_type="10-K",
            filed_date="2024-12-31",
            source=None,
            snippet="AREC filing snippet.",
        ),
    ]
    citations = pipeline._to_citations(chunks)

    monkeypatch.setattr(
        ChatPipeline,
        "_market_context_lines",
        lambda self, symbols: (
            ["- Benchmark SPY: ...", "- AEM: ...", "- AREC: ..."],
            ["AEM", "AREC"],
            {
                "window": "2024-01-01..2024-12-31",
                "benchmark": "SPY",
                "symbols": list(symbols),
                "metrics": [],
            },
        ),
    )

    context_text, context_meta = pipeline._build_external_context(
        question="How do geopolitics affect neodymium pricing?",
        citations=citations,
    )

    assert "Market context" in context_text
    assert context_meta["market_context_items"] == 3
    assert context_meta["market_context_requested_symbols"] == [
        "AEM",
        "AREC",
    ]
    assert context_meta["market_context_symbols"] == ["AEM", "AREC"]


def test_build_external_context_calls_market_bundle_once_for_multi_symbol(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["AEM", "AREC"],
        question="Compare issuer risk signals.",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        include_market_context=True,
        include_news_context=False,
    )
    pipeline = ChatPipeline(config=config)
    citations = pipeline._to_citations(
        [
            _RetrievedChunk(
                collection="retrieve",
                score=0.9,
                symbol="AEM",
                accession_number="A1",
                form_type="10-K",
                filed_date="2024-12-31",
                source=None,
                snippet="AEM filing snippet.",
            ),
            _RetrievedChunk(
                collection="retrieve",
                score=0.89,
                symbol="AREC",
                accession_number="B1",
                form_type="10-K",
                filed_date="2024-12-31",
                source=None,
                snippet="AREC filing snippet.",
            ),
        ]
    )

    observed_calls = {"value": 0}
    observed_symbols: list[str] = []

    def _fake_market_context_lines(self, *, symbols):
        observed_calls["value"] += 1
        observed_symbols[:] = list(symbols)
        return (
            ["- Benchmark SPY: ...", "- AEM: ...", "- AREC: ..."],
            ["AEM", "AREC"],
            {
                "window": "2024-01-01..2024-12-31",
                "benchmark": "SPY",
                "symbols": list(symbols),
                "metrics": [],
            },
        )

    monkeypatch.setattr(
        ChatPipeline,
        "_market_context_lines",
        _fake_market_context_lines,
    )

    context_text, context_meta = pipeline._build_external_context(
        question="Compare issuer risk signals.",
        citations=citations,
    )

    assert "Market context" in context_text
    assert observed_calls["value"] == 1
    assert observed_symbols == ["AEM", "AREC"]
    assert context_meta["market_context_items"] == 3


def test_build_prompt_adds_ticker_disambiguation_rules(tmp_path: Path) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["AEM", "AREC"],
        question="Compare issuer risk signals.",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
    )
    pipeline = ChatPipeline(config=config)
    chunks = [
        _RetrievedChunk(
            collection="retrieve",
            score=0.9,
            symbol="AEM",
            accession_number="A1",
            form_type="10-K",
            filed_date="2024-12-31",
            source=None,
            snippet="AEM filing snippet.",
        ),
        _RetrievedChunk(
            collection="retrieve",
            score=0.89,
            symbol="AREC",
            accession_number="B1",
            form_type="10-K",
            filed_date="2024-12-31",
            source=None,
            snippet="AREC filing snippet.",
        ),
    ]
    citations = pipeline._to_citations(chunks)

    prompt = pipeline._build_prompt(
        question="Compare issuer risk signals.",
        citations=citations,
        external_context="",
    )

    assert "Treat each ticker symbol as a distinct issuer." in prompt
    assert "Never claim two different tickers are the same entity" in prompt
    assert "Ticker scope:\nAEM, AREC" in prompt
    assert "Symbols with retrieved filing evidence:\nAEM, AREC" in prompt
    assert "Symbols without retrieved filing evidence:\n(none)" in prompt


def test_symbol_coverage_metadata_tracks_missing_symbols(
    tmp_path: Path,
) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["AEM", "AREC", "ALB"],
        question="Compare issuer risk signals.",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
    )
    pipeline = ChatPipeline(config=config)
    chunks = [
        _RetrievedChunk(
            collection="retrieve",
            score=0.9,
            symbol="AEM",
            accession_number="A1",
            form_type="10-K",
            filed_date="2024-12-31",
            source=None,
            snippet="AEM filing snippet.",
        ),
        _RetrievedChunk(
            collection="retrieve",
            score=0.89,
            symbol="ALB",
            accession_number="B1",
            form_type="10-K",
            filed_date="2024-12-31",
            source=None,
            snippet="ALB filing snippet.",
        ),
    ]
    citations = pipeline._to_citations(chunks)
    metadata = pipeline._symbol_coverage_metadata(citations)

    assert metadata["requested_symbols"] == ["AEM", "AREC", "ALB"]
    assert metadata["retrieved_symbols"] == ["AEM", "ALB"]
    assert metadata["missing_symbols"] == ["AREC"]


def test_select_context_chunks_reserves_requested_symbol_coverage(
    tmp_path: Path,
) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["AEM", "AREC"],
        question="What changed?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        top_k=3,
        per_symbol_min_chunks=1,
    )
    pipeline = ChatPipeline(config=config)
    chunks = [
        _RetrievedChunk(
            collection="retrieve",
            score=0.99,
            symbol="AEM",
            accession_number="1",
            form_type="6-K",
            filed_date="2024-01-01",
            source=None,
            snippet="aem-1",
        ),
        _RetrievedChunk(
            collection="retrieve",
            score=0.98,
            symbol="AEM",
            accession_number="2",
            form_type="6-K",
            filed_date="2024-01-02",
            source=None,
            snippet="aem-2",
        ),
        _RetrievedChunk(
            collection="retrieve",
            score=0.97,
            symbol="AREC",
            accession_number="3",
            form_type="10-K",
            filed_date="2024-01-03",
            source=None,
            snippet="arec-1",
        ),
    ]

    selected = pipeline._select_context_chunks(chunks)
    selected_symbols = [chunk.symbol for chunk in selected]
    assert selected_symbols.count("AEM") >= 1
    assert selected_symbols.count("AREC") >= 1


def test_pack_context_citations_enforces_token_budget(tmp_path: Path) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["CDE"],
        question="What changed?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        top_k=4,
        max_context_chunks=4,
        context_token_budget=500,
    )
    pipeline = ChatPipeline(config=config)
    citations = pipeline._to_citations(
        [
            _RetrievedChunk(
                collection="retrieve",
                score=0.9,
                symbol="CDE",
                accession_number="1",
                form_type="10-K",
                filed_date="2024-01-01",
                source=None,
                snippet="This is a long context chunk " * 300,
            ),
            _RetrievedChunk(
                collection="retrieve",
                score=0.8,
                symbol="CDE",
                accession_number="2",
                form_type="10-K",
                filed_date="2024-01-02",
                source=None,
                snippet="Second chunk should likely be excluded by budget.",
            ),
        ]
    )

    packed = pipeline._pack_context_citations(citations)
    assert len(packed) >= 1
    assert packed[0][0].citation_id == "C1"
    assert len(packed[0][1]) < len(citations[0].snippet)
    total_tokens = 0
    for citation, snippet in packed:
        total_tokens += pipeline._estimate_tokens(
            f"Collection={citation.collection}"
        )
        total_tokens += pipeline._estimate_tokens(snippet)
    assert total_tokens <= config.context_token_budget


def test_invoke_llm_with_timeout_raises(tmp_path: Path) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["CDE"],
        question="What changed?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        llm_timeout_seconds=1,
    )
    pipeline = ChatPipeline(config=config)

    class _SlowLLM:
        def invoke(self, prompt: str) -> str:
            time.sleep(2)
            return "never reached"

    with pytest.raises(TimeoutError):
        pipeline._invoke_llm_with_timeout(llm=_SlowLLM(), prompt="x")


def test_effective_max_new_tokens_respects_cap(tmp_path: Path) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["CDE"],
        question="What changed?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        max_context_chunks=10,
        generation_token_cap=256,
    )
    pipeline = ChatPipeline(config=config)

    assert pipeline._effective_max_new_tokens(1) == 128
    assert pipeline._effective_max_new_tokens(8) == 256
    assert pipeline._effective_max_new_tokens(20) == 256
    assert pipeline._effective_context_token_budget(1) == 512
    assert pipeline._effective_context_token_budget(8) == 1024


def test_chat_pipeline_run_requires_question(tmp_path: Path) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["CDE"],
        question=None,
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
    )

    result = ChatPipeline(config=config).run()

    assert result.success is False
    assert result.error is not None
    assert "requires a question" in result.error
