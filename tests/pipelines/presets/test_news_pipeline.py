# tests/pipelines/presets/test_news_pipeline.py
"""Tests for the news pipeline and supporting step helpers."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sec_nlp.pipelines.presets.news.config import NewsSettings
from sec_nlp.pipelines.presets.news.models import (
    FilingEvent,
    NewsCorrelation,
    NewsHeadline,
    NewsTimelineEntry,
)
from sec_nlp.pipelines.presets.news.pipeline import NewsPipeline
from sec_nlp.pipelines.presets.news.run_stages import (
    NewsRunState,
    build_news_stage_chain,
)
from sec_nlp.pipelines.presets.news.steps.correlate import correlate_news_items
from sec_nlp.pipelines.presets.news.steps.fetch import (
    parse_feed_specs,
    resolve_symbol_aliases,
)
from sec_nlp.pipelines.presets.news.steps.match import match_news_items


def _headline(
    *,
    published_at: str,
    published_date: str,
    title: str,
    score: float = 0.0,
) -> NewsHeadline:
    return NewsHeadline(
        symbol="ABC",
        title=title,
        url=f"https://example.com/{title.replace(' ', '_')}",
        source="SampleFeed",
        published_at=published_at,
        published_date=published_date,
        snippet="sample snippet",
        matched_keywords=["ABC"],
        relevance_score=score,
    )


def test_parse_feed_specs_supports_url_and_pipe_format() -> None:
    parsed = parse_feed_specs(
        [
            "https://example.com/feed.xml",
            "https://newsapi.org/v2/everything?q=abc|json_api|NewsAPI",
            "https://example.com/feed.xml",  # duplicate URL should be deduped
        ]
    )

    assert parsed == [
        ("https://example.com/feed.xml", "rss", "example.com"),
        (
            "https://newsapi.org/v2/everything?q=abc",
            "json_api",
            "NewsAPI",
        ),
    ]


def test_match_news_items_filters_on_min_relevance(monkeypatch) -> None:
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.news.steps.match._efts_score",
        lambda text, topics: (
            [topic for topic in topics if topic.lower() in text.lower()],
            (
                len(
                    [topic for topic in topics if topic.lower() in text.lower()]
                )
                / len(topics)
            ),
        ),
    )

    items = [
        _headline(
            published_at="2026-02-14T12:00:00+00:00",
            published_date="2026-02-14",
            title="ABC supply chain update",
        ),
        _headline(
            published_at="2026-02-14T08:00:00+00:00",
            published_date="2026-02-14",
            title="Generic macro commentary",
        ),
    ]

    matched = match_news_items(
        items=items,
        symbol="ABC",
        topics=["supply", "recall"],
        min_relevance=0.5,
    )

    assert len(matched) == 1
    assert matched[0].title == "ABC supply chain update"
    assert matched[0].relevance_score == 0.5


def test_match_news_items_requires_symbol_match_by_default(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.news.steps.match._efts_score",
        lambda text, topics: (
            [topic for topic in topics if topic.lower() in text.lower()],
            (
                len(
                    [topic for topic in topics if topic.lower() in text.lower()]
                )
                / len(topics)
            ),
        ),
    )

    items = [
        NewsHeadline(
            symbol="ABC",
            title="Industry production update",
            url="https://example.com/industry",
            source="SampleFeed",
            published_at="2026-02-14T12:00:00+00:00",
            published_date="2026-02-14",
            snippet="General commentary unrelated to issuer.",
            matched_keywords=["production"],
        ),
        NewsHeadline(
            symbol="ABC",
            title="ABC production guidance update",
            url="https://example.com/abc",
            source="SampleFeed",
            published_at="2026-02-14T11:00:00+00:00",
            published_date="2026-02-14",
            snippet="Issuer guidance",
            matched_keywords=["ABC", "production"],
        ),
    ]

    matched = match_news_items(
        items=items,
        symbol="ABC",
        topics=["production", "guidance"],
        min_relevance=0.5,
    )

    assert len(matched) == 1
    assert matched[0].title == "ABC production guidance update"


def test_match_news_items_accepts_company_alias_anchor(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.news.steps.match._efts_score",
        lambda text, topics: (
            [topic for topic in topics if topic.lower() in text.lower()],
            (
                len(
                    [topic for topic in topics if topic.lower() in text.lower()]
                )
                / len(topics)
            ),
        ),
    )

    items = [
        NewsHeadline(
            symbol="CDE",
            title="Coeur Mining raises production guidance",
            url="https://example.com/coeur",
            source="SampleFeed",
            published_at="2026-02-14T11:00:00+00:00",
            published_date="2026-02-14",
            snippet="Company update",
            matched_keywords=["Coeur Mining", "production", "guidance"],
        ),
        NewsHeadline(
            symbol="CDE",
            title="Industry production guidance update",
            url="https://example.com/industry",
            source="SampleFeed",
            published_at="2026-02-14T10:00:00+00:00",
            published_date="2026-02-14",
            snippet="Generic commentary",
            matched_keywords=["production", "guidance"],
        ),
    ]

    matched = match_news_items(
        items=items,
        symbol="CDE",
        topics=["production", "guidance"],
        min_relevance=1.0,
        symbol_aliases=["CDE", "Coeur Mining"],
    )

    assert len(matched) == 1
    assert matched[0].title == "Coeur Mining raises production guidance"


def test_resolve_symbol_aliases_adds_company_name_variants(
    monkeypatch,
) -> None:
    settings = NewsSettings(
        email="alias-test@example.com",
        symbols=["CDE"],
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.news.steps.fetch.get_company_name_for_ticker",
        lambda **_: "Coeur Mining, Inc.",
    )

    aliases = resolve_symbol_aliases(symbol="CDE", settings=settings)

    assert aliases[0] == "CDE"
    assert "$CDE" in aliases
    assert "Coeur Mining, Inc." in aliases
    assert "Coeur Mining" in aliases
    assert "Coeur" in aliases


def test_correlate_news_items_links_filings_and_market(
    monkeypatch, tmp_path: Path
) -> None:
    settings = NewsSettings(
        email="test@example.com",
        symbols=["ABC"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        include_market_context=True,
        cluster_threshold=2,
        cluster_gap_days=1,
    )

    items = [
        _headline(
            published_at="2026-02-10T12:00:00+00:00",
            published_date="2026-02-10",
            title="ABC supply chain update",
            score=0.8,
        ),
        _headline(
            published_at="2026-02-10T15:00:00+00:00",
            published_date="2026-02-10",
            title="ABC supplier expansion",
            score=0.75,
        ),
        _headline(
            published_at="2026-02-11T12:00:00+00:00",
            published_date="2026-02-11",
            title="ABC recall expands",
            score=0.7,
        ),
    ]

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.news.steps.correlate._collect_filing_events",
        lambda symbol, settings, start_date, end_date: [
            FilingEvent(
                filing_date="2026-02-11",
                form_type="8-K",
                accession_number="0000000000-26-000001",
            )
        ],
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.news.steps.correlate._build_market_series",
        lambda symbol, include_market_context, start_date, end_date: (
            {
                # close prices by date
                date(2026, 2, 10): 10.0,
                date(2026, 2, 11): 10.5,
            },
            {
                # returns by date
                date(2026, 2, 10): 0.01,
                date(2026, 2, 11): 0.03,
            },
        ),
    )

    correlated_items, timeline, correlation = correlate_news_items(
        symbol="ABC",
        items=items,
        settings=settings,
    )

    assert len(correlated_items) == 3
    assert correlated_items[1].nearest_filing_form == "8-K"
    assert len(timeline) == 2
    assert correlation.days_compared == 2
    assert correlation.news_to_return_correlation is not None
    assert len(correlation.clusters) == 1


def test_pipeline_run_writes_outputs_with_mocked_steps(
    tmp_path: Path, monkeypatch
) -> None:
    config = NewsSettings(
        email="test@example.com",
        symbols=["ABC"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        output_format="all",
        topics=["supply"],
    )

    fetched_items = [
        _headline(
            published_at="2026-02-12T12:00:00+00:00",
            published_date="2026-02-12",
            title="ABC supply chain update",
        )
    ]
    matched_items = [
        fetched_items[0].model_copy(
            update={"matched_topics": ["supply"], "relevance_score": 1.0}
        )
    ]
    correlation = NewsCorrelation(
        news_to_return_correlation=0.25,
        days_compared=1,
        days_with_news=1,
        days_with_market_data=1,
        average_daily_headlines=1.0,
        filings_linked=0,
    )
    timeline = [
        NewsTimelineEntry(
            date="2026-02-12",
            headline_count=1,
            headlines=matched_items,
            filings=[],
            market_close=10.0,
            market_return=0.02,
        )
    ]

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.news.run_stages.fetch_news_items",
        lambda symbol, settings: fetched_items,
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.news.run_stages.resolve_symbol_aliases",
        lambda symbol, settings: ["ABC", "$ABC"],
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.news.run_stages.match_news_items",
        lambda items, symbol, topics, min_relevance, require_symbol_match, symbol_aliases: (
            matched_items
        ),
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.news.run_stages.correlate_news_items",
        lambda symbol, items, settings: (matched_items, timeline, correlation),
    )

    pipeline = NewsPipeline(config=config)
    result = pipeline.run()

    assert result.success is True
    assert result.symbols_processed == 1
    assert result.items_fetched == 1
    assert result.items_emitted == 1
    assert len(result.outputs) == 3

    json_path = next(path for path in result.outputs if path.suffix == ".json")
    payload = json.loads(json_path.read_text())
    expected_short_id = config.short_id if config.short_id > 0 else None
    assert payload["run_id"] == str(config.run_id)
    assert payload["run_short_id"] == expected_short_id
    assert isinstance(payload["run_timestamp"], str)

    csv_path = next(path for path in result.outputs if path.suffix == ".csv")
    lines = csv_path.read_text().splitlines()
    assert lines[0].startswith("# run_timestamp:")
    assert lines[1].startswith("# run_short_id:")
    assert lines[2].startswith("# run_id:")
    assert lines[3].startswith("# run_short_id_display:")
    assert lines[4].startswith("symbol,published_date")


def test_news_stage_chain_preserves_state_identity(
    tmp_path: Path, monkeypatch
) -> None:
    config = NewsSettings(
        email="test@example.com",
        symbols=["ABC"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        output_format="json",
    )
    pipeline = NewsPipeline(config=config)
    monkeypatch.setattr(
        NewsPipeline,
        "_write_outputs",
        lambda self, **_kwargs: [],
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.news.run_stages.fetch_news_items",
        lambda symbol, settings: [],
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.news.run_stages.resolve_symbol_aliases",
        lambda symbol, settings: [symbol],
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.news.run_stages.match_news_items",
        lambda items, symbol, topics, min_relevance, require_symbol_match, symbol_aliases: [],
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.news.run_stages.correlate_news_items",
        lambda symbol, items, settings: ([], [], NewsCorrelation()),
    )

    chain = build_news_stage_chain(pipeline)
    initial_state = NewsRunState(
        runtime=pipeline,
        symbol="ABC",
        progress=None,
        phase_task=None,
    )
    initial_state_id = id(initial_state)
    final_state = pipeline.run_stage_chain(
        initial_state=initial_state,
        stage_chain=chain,
    )

    assert id(final_state) == initial_state_id
