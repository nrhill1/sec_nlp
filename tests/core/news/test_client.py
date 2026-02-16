"""Tests for the newswatch Rust extension Python wrapper."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sec_nlp.core.news import client


def test_load_newswatch_module_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client._load_newswatch_module.cache_clear()

    def fail_import(_name: str):
        raise RuntimeError("boom")

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
    calls: dict[str, object] = {}

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
    assert calls["fetch"] == (["supply chain"], 5)
    assert items[0].title == "Acme supply chain update"
    assert items[0].matched_keywords == ["supply chain"]


def test_news_retriever_requires_non_empty_feeds() -> None:
    with pytest.raises(ValueError, match="feeds must be non-empty"):
        client.NewsRetriever(
            [], "SEC NLP Tool (you@example.com)", module=SimpleNamespace()
        )
