# tests/core/news/test_client.py
"""Tests for the newswatch Rust extension Python wrapper."""

from __future__ import annotations

from types import ModuleType, SimpleNamespace

import pytest

from sec_nlp.core.news import client


def test_load_newswatch_module_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client._load_newswatch_module.cache_clear()

    def fail_import(_name: str):
        raise ImportError("boom")

    monkeypatch.setattr(client, "import_module", fail_import)

    with pytest.raises(
        client.NewswatchExtensionError,
        match="newswatch extension is not available",
    ):
        client._load_newswatch_module()

    client._load_newswatch_module.cache_clear()


def test_news_retriever_fetch_maps_native_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, tuple] = {}

    raw_item = SimpleNamespace(
        title="Acme supply chain update",
        url="https://example.com/acme",
        source="Sample Feed",
        published_at="2025-02-10T12:00:00Z",
        matched_keywords=["supply chain"],
        snippet="Supplier network expanded.",
    )

    fake_client = SimpleNamespace(
        fetch=lambda keywords, max_results: (
            calls.setdefault("fetch", (keywords, max_results)),
            [raw_item],
        )[1]
    )
    fake_module = SimpleNamespace(
        NewsClient=lambda feeds, user_agent, rate_limit_secs: (
            calls.setdefault(
                "constructor", (feeds, user_agent, rate_limit_secs)
            ),
            fake_client,
        )[1]
    )

    monkeypatch.setattr(client, "_load_newswatch_module", lambda: fake_module)

    retriever = client.create_news_retriever(
        "SEC NLP Tool (you@example.com)",
        feeds=[("https://example.com/feed.xml", "rss", "Sample Feed")],
        rate_limit_secs=0.25,
    )
    items = retriever.fetch(["supply chain"], max_results=5)

    assert calls["constructor"] == (
        [("https://example.com/feed.xml", "rss", "Sample Feed")],
        "SEC NLP Tool (you@example.com)",
        0.25,
    )
    assert calls["fetch"] == (["supply chain"], 500)
    assert items[0].title == "Acme supply chain update"
    assert items[0].matched_keywords == ["supply chain"]


def test_news_retriever_requires_non_empty_feeds() -> None:
    with pytest.raises(ValueError, match="feeds must be non-empty"):
        client.NewsRetriever(
            [],
            "SEC NLP Tool (you@example.com)",
            module=ModuleType("newswatch_test_module"),
        )


def test_create_news_retriever_reuses_cached_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client._cached_news_retriever.cache_clear()
    client._load_newswatch_module.cache_clear()
    constructor_calls = 0

    fake_client = SimpleNamespace(fetch=lambda keywords, max_results: [])

    def _construct(feeds, user_agent, rate_limit_secs):
        nonlocal constructor_calls
        constructor_calls += 1
        assert feeds == [("https://example.com/feed.xml", "rss", "Sample Feed")]
        assert user_agent == "SEC NLP Tool (cache@example.com)"
        assert rate_limit_secs == 0.15
        return fake_client

    fake_module = SimpleNamespace(NewsClient=_construct)
    monkeypatch.setattr(client, "_load_newswatch_module", lambda: fake_module)

    first = client.create_news_retriever(
        "SEC NLP Tool (cache@example.com)",
        feeds=[("https://example.com/feed.xml", "rss", "Sample Feed")],
        rate_limit_secs=0.15,
    )
    second = client.create_news_retriever(
        "SEC NLP Tool (cache@example.com)",
        feeds=[("https://example.com/feed.xml", "rss", "Sample Feed")],
        rate_limit_secs=0.15,
    )

    assert first is second
    assert constructor_calls == 1

    client._cached_news_retriever.cache_clear()


def test_normalization_preserves_recurring_releases_and_unknown_dates() -> None:
    items = [
        client.NewsItem(
            title="Policy statement",
            url=f"https://example.com/{idx}",
            source="Central bank",
            published_at=stamp,
        )
        for idx, stamp in enumerate(
            [
                "2026-01-28",
                "2026-03-18",
                "Wed, 18 Mar 2026 12:00:00 GMT",
                None,
                None,
            ]
        )
    ]
    normalized = client.normalize_news_items(items)
    assert len(normalized) == 4
    assert normalized[0].published_at is not None
    assert normalized[0].published_at.startswith("2026-03-18")
    assert normalized[-1].published_at is None


def test_sec_feed_requests_use_shared_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        client,
        "fetch_sec_bytes",
        lambda *_: (
            b"<rss><channel><item><title>SEC update</title><link>https://www.sec.gov/news/example</link><pubDate>Fri, 25 Sep 2026 12:00:00 GMT</pubDate></item></channel></rss>"
        ),
    )
    module = ModuleType("native_must_not_fetch")
    retriever = client.NewsRetriever(
        [("https://www.sec.gov/news/pressreleases.rss", "rss", "SEC")],
        "Test test@example.com",
        module=module,
    )
    items = retriever.fetch([])
    assert len(items) == 1 and items[0].source == "SEC"
