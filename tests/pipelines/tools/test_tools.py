"""Tests for reusable LangChain tool wrappers."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from sec_nlp.core.market_analytics import (
    MarketContextBundle,
    MarketContextMetric,
)
from sec_nlp.core.news.client import NewsItem
from sec_nlp.pipelines.tools import (
    market_context_tool,
    news_context_tool,
    qdrant_search_tool,
    retrieve_hits_tool,
)
from sec_nlp.types import JsonValue


def test_market_context_tool_returns_structured_payload(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "sec_nlp.pipelines.tools.market.build_market_context",
        lambda **kwargs: MarketContextBundle(
            window="2024-01-01..2024-01-31",
            benchmark="SPY",
            symbols=["AAA"],
            metrics=[
                MarketContextMetric(
                    symbol="AAA",
                    return_pct=1.2,
                    benchmark_return_pct=0.8,
                    spread_pct=0.4,
                    beta=1.1,
                    std_dev=0.02,
                    atr=0.5,
                    max_drawdown=3.0,
                    volume_spike=1.3,
                    observations=20,
                )
            ],
        ),
    )

    market_input: dict[str, JsonValue] = {
        "symbols": ["AAA"],
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
        "profile": "compact",
    }
    payload = market_context_tool.invoke(market_input)
    assert isinstance(payload, dict)

    assert payload["window"] == "2024-01-01..2024-01-31"
    assert payload["benchmark"] == "SPY"
    assert payload["symbols"] == ["AAA"]
    assert len(payload["metrics"]) == 1
    assert payload["metrics"][0]["symbol"] == "AAA"
    assert payload["lines"]


def test_retrieve_hits_tool_returns_hits(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "sec_nlp.pipelines.tools.retrieve.run_candidate_search",
        lambda symbol, queries, settings: {
            queries[0]: [
                SimpleNamespace(
                    accession_number="0000123456-26-000001",
                    cik="0000123456",
                    company_name="Sample Co",
                    form_type="10-K",
                    filed_date=date(2026, 2, 1),
                    score=0.9,
                    edgar_url="https://example.com",
                    snippet="sample snippet",
                )
            ]
        },
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.tools.retrieve.rank_retrieval_hits",
        lambda symbol, candidates_by_query, top_k: [
            SimpleNamespace(
                model_dump=lambda mode, exclude_none: {
                    "symbol": symbol,
                    "query": "supply chain",
                    "accession_number": "0000123456-26-000001",
                    "form_type": "10-K",
                    "filed_date": "2026-02-01",
                    "company_name": "Sample Co",
                    "cik": "0000123456",
                    "score": 0.9,
                    "edgar_url": "https://example.com",
                    "snippet": "sample snippet",
                }
            )
        ],
    )

    retrieve_input: dict[str, JsonValue] = {
        "symbols": ["AAA"],
        "queries": ["supply chain"],
        "top_k": 5,
        "collection": "retrieve_x",
    }
    payload = retrieve_hits_tool.invoke(retrieve_input)
    assert isinstance(payload, dict)

    assert payload["collection"] == "retrieve_x"
    assert payload["run_metadata"]["symbols_processed"] == 1
    assert payload["run_metadata"]["queries_processed"] == 1
    assert payload["run_metadata"]["hits_returned"] == 1
    assert len(payload["hits"]) == 1


def test_retrieve_hits_tool_enforces_top_k_bound() -> None:
    with pytest.raises(ValueError):
        limit_input: dict[str, JsonValue] = {
            "queries": ["supply chain"],
            "top_k": 201,
        }
        retrieve_hits_tool.invoke(limit_input)


def test_qdrant_search_tool_returns_hits(monkeypatch) -> None:
    class _FakeEmbedder:
        def embed_query(self, query: str) -> list[float]:
            return [0.1, 0.2]

    class _FakeQdrant:
        def collection_exists(self, collection: str) -> bool:
            return True

        def query_points(self, **kwargs):
            point = SimpleNamespace(
                score=0.91,
                payload={
                    "symbol": "AAA",
                    "accession_number": "0000123456-26-000001",
                    "form_type": "10-K",
                    "filed_date": "2026-02-01",
                    "source": "https://example.com",
                    "snippet": "sample chunk",
                },
            )
            return SimpleNamespace(points=[point])

    monkeypatch.setattr(
        "sec_nlp.pipelines.tools.vector.VectorConfig.setup_embedding_model",
        lambda self: (_FakeEmbedder(), 2),
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.tools.vector.VectorConfig.setup_qdrant_client",
        lambda self: _FakeQdrant(),
    )

    qdrant_input: dict[str, JsonValue] = {
        "collection": "retrieve",
        "query": "supply chain risk",
        "top_k": 5,
        "symbols": ["AAA"],
        "forms": ["10-K"],
    }
    payload = qdrant_search_tool.invoke(qdrant_input)
    assert isinstance(payload, dict)

    assert payload["collection"] == "retrieve"
    assert payload["query"] == "supply chain risk"
    assert payload["hit_count"] == 1
    assert payload["hits"][0]["symbol"] == "AAA"


def test_news_context_tool_filters_and_dedupes(monkeypatch) -> None:
    now = datetime.now(UTC)
    older = now - timedelta(days=30)

    class _FakeRetriever:
        def fetch(self, keywords: list[str], max_results: int):
            return [
                NewsItem(
                    title="Rare earth update",
                    url="https://example.com/1",
                    source="Feed A",
                    published_at=now.isoformat(),
                    matched_keywords=["rare earth"],
                    snippet="fresh",
                ),
                NewsItem(
                    title="Rare earth update",
                    url="https://example.com/1",
                    source="Feed A",
                    published_at=now.isoformat(),
                    matched_keywords=["rare earth"],
                    snippet="duplicate",
                ),
                NewsItem(
                    title="Old item",
                    url="https://example.com/2",
                    source="Feed B",
                    published_at=older.isoformat(),
                    matched_keywords=["rare earth"],
                    snippet="old",
                ),
            ]

    monkeypatch.setattr(
        "sec_nlp.pipelines.tools.news.create_news_retriever",
        lambda **kwargs: _FakeRetriever(),
    )

    news_input: dict[str, JsonValue] = {
        "keywords": ["rare earth"],
        "max_results": 10,
        "lookback_days": 14,
    }
    payload = news_context_tool.invoke(news_input)
    assert isinstance(payload, dict)

    assert payload["lookback_days"] == 14
    assert len(payload["items"]) == 1
    assert payload["items"][0]["title"] == "Rare earth update"
