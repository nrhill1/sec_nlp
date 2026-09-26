# tests/app/investing/test_service.py
"""Tests for investing brief dates, source isolation, matching, and synthetic data."""

from datetime import UTC, date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from pydantic import HttpUrl

from sec_nlp.app.investing import service
from sec_nlp.app.investing.models import (
    Brief,
    Feed,
    Headline,
    InvestingSettings,
    JournalEntry,
    Theme,
    WatchItem,
)
from sec_nlp.core.market import MarketQuote, MarketRetriever
from sec_nlp.core.news.client import NewsItem, NewsRetriever

_NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)


def _settings() -> InvestingSettings:
    """Return a small workspace with no implicit company sources."""
    return InvestingSettings(
        watchlist=(
            WatchItem(
                symbol="AAPL", name="Apple", aliases=("Cupertino company",)
            ),
        ),
        benchmarks=("AAPL", "SPY"),
        company_feeds=False,
        feeds=(Feed(name="General", url=HttpUrl("https://example.com/feed")),),
        themes=(
            Theme(
                name="Rates",
                keywords=("interest rates",),
                question="How have financing assumptions changed?",
            ),
        ),
    )


def _quote(
    day: int, close: float, adjusted: float | None = None, *, hour: int = 20
) -> MarketQuote:
    """Return an internally consistent quote for a September UTC session."""
    return MarketQuote(
        timestamp=int(datetime(2026, 9, day, hour, tzinfo=UTC).timestamp()),
        open_price=close,
        high=close + 1,
        low=max(0.001, close - 1),
        close=close,
        volume=100,
        adjclose=adjusted if adjusted is not None else close,
    )


def _news(
    title: str, slug: str, *, published: str | None = "2026-09-25T12:00:00Z"
) -> NewsItem:
    """Return a source headline with an explicit optional publication date."""
    return NewsItem(
        title=title,
        url=f"https://example.com/{slug}",
        source="provider",
        published_at=published,
    )


def _brief(
    settings: InvestingSettings, headlines: tuple[Headline, ...] = ()
) -> Brief:
    """Return a prior live snapshot compatible with the fixed report time."""
    return Brief(
        brief_id="a" * 32,
        generated_at=_NOW - timedelta(days=1),
        settings=settings,
        headlines=headlines,
    )


def test_market_uses_adjusted_sessions_and_keeps_dated_raw_close() -> None:
    """Compute returns after removing future, invalid, and duplicate sessions."""
    settings = _settings()
    retriever = MagicMock(spec=MarketRetriever)
    quotes = [_quote(day, 190 + day, 80 + day) for day in range(18, 24)]
    quotes.extend(
        [
            _quote(23, 219, 104, hour=21),
            _quote(27, 999),
            _quote(24, float("nan")),
            _quote(25, 210, 0),
        ]
    )
    retriever.retrieve_range.side_effect = [
        list(reversed(quotes)),
        [_quote(25, 45)],
    ]
    news = MagicMock(spec=NewsRetriever)
    news.fetch.return_value = []
    with (
        patch.object(
            service, "create_market_retriever", return_value=retriever
        ),
        patch.object(service, "create_news_retriever", return_value=news),
    ):
        brief = service.build_brief(settings, now=_NOW)
    apple, benchmark = brief.market
    assert apple.observations == 6
    assert apple.close == 219
    assert apple.quote_date == date(2026, 9, 23)
    assert apple.change_1d_pct == pytest.approx((104 / 102 - 1) * 100)
    assert apple.change_5d_pct == pytest.approx((104 / 98 - 1) * 100)
    assert not apple.stale
    assert benchmark.change_1d_pct is None
    assert benchmark.change_5d_pct is None
    assert retriever.retrieve_range.call_count == 2
    retriever.retrieve_range.assert_any_call(
        "AAPL", (date(2026, 8, 22), date(2026, 9, 27))
    )


def test_market_partial_failure_staleness_and_empty_are_distinct() -> None:
    """Preserve independent stale, failed, and missing symbol observations."""
    settings = _settings().model_copy(update={"benchmarks": ("SPY", "QQQ")})
    market = MagicMock(spec=MarketRetriever)
    market.retrieve_range.side_effect = [
        [_quote(18, 10), _quote(19, 11)],
        RuntimeError("provider unavailable"),
        [],
    ]
    news = MagicMock(spec=NewsRetriever)
    news.fetch.return_value = []
    with (
        patch.object(service, "create_market_retriever", return_value=market),
        patch.object(service, "create_news_retriever", return_value=news),
    ):
        brief = service.build_brief(settings, now=_NOW)
    assert brief.market[0].stale
    assert brief.market[0].change_1d_pct == pytest.approx(10)
    assert brief.market[0].change_5d_pct is None
    assert brief.market[1].close is None
    assert brief.market[2].quote_date is None
    assert [item.status for item in brief.sources] == [
        "ok",
        "error",
        "empty",
        "empty",
    ]
    assert "provider unavailable" in brief.sources[1].detail
    assert "stale" in brief.sources[0].detail


def test_failed_market_setup_does_not_block_news() -> None:
    """Report unavailable optional market extensions while retaining headlines."""
    news = MagicMock(spec=NewsRetriever)
    news.fetch.return_value = [_news("General economic update", "current")]
    with (
        patch.object(
            service,
            "create_market_retriever",
            side_effect=ImportError("not built"),
        ),
        patch.object(service, "create_news_retriever", return_value=news),
    ):
        brief = service.build_brief(_settings(), now=_NOW)
    assert len(brief.headlines) == 1
    assert brief.headlines[0].symbols == ()
    assert [item.status for item in brief.sources] == ["error", "error", "ok"]


def test_news_sources_are_independent_and_company_feeds_are_scoped() -> None:
    """Fetch all configured sources separately and label company-only evidence."""
    settings = _settings().model_copy(
        update={
            "watchlist": (WatchItem(symbol="AAPL"),),
            "benchmarks": (),
            "company_feeds": True,
            "feeds": (
                Feed(name="Broken", url=HttpUrl("https://example.com/broken")),
                Feed(name="Macro", url=HttpUrl("https://example.com/macro")),
            ),
        }
    )
    market = MagicMock(spec=MarketRetriever)
    market.retrieve_range.return_value = []
    macro = MagicMock(spec=NewsRetriever)
    macro.fetch.return_value = [_news("World economic release", "macro")]
    company = MagicMock(spec=NewsRetriever)
    company.fetch.return_value = [
        _news("Board appoints new executive", "company")
    ]
    with (
        patch.object(service, "create_market_retriever", return_value=market),
        patch.object(
            service,
            "create_news_retriever",
            side_effect=[RuntimeError("bad feed"), macro, company],
        ) as factory,
    ):
        brief = service.build_brief(settings, now=_NOW)
    assert factory.call_count == 3
    factory.assert_any_call(
        user_agent=settings.user_agent,
        feeds=[
            (
                "https://finance.yahoo.com/rss/headline?s=AAPL",
                "rss",
                "Yahoo Finance: AAPL",
            )
        ],
    )
    for call in factory.call_args_list:
        assert len(call.kwargs["feeds"]) == 1
    macro.fetch.assert_called_once_with(keywords=[], max_results=500)
    company.fetch.assert_called_once_with(keywords=[], max_results=500)
    assert [item.status for item in brief.sources] == [
        "empty",
        "error",
        "ok",
        "ok",
    ]
    by_title = {item.title: item for item in brief.headlines}
    assert by_title["World economic release"].symbols == ()
    assert by_title["Board appoints new executive"].symbols == ("AAPL",)
    assert (
        by_title["Board appoints new executive"].source == "Yahoo Finance: AAPL"
    )


def test_news_dates_are_utc_and_invalid_or_missing_dates_remain_visible() -> (
    None
):
    """Filter exact future and lookback dates while retaining unknown dates."""
    news = MagicMock(spec=NewsRetriever)
    news.fetch.return_value = [
        _news("At cutoff", "cutoff", published="2026-09-19T07:00:00-05:00"),
        _news("RFC date", "rfc", published="Fri, 25 Sep 2026 09:00:00 -0500"),
        _news("Naive UTC date", "naive", published="2026-09-25T13:00:00"),
        _news("Future later today", "future", published="2026-09-26T13:00:00Z"),
        _news("Before cutoff", "old", published="2026-09-19T11:59:59Z"),
        _news("Unknown date", "unknown", published="nonsense"),
        _news("No date", "missing", published=None),
    ]
    with patch.object(service, "create_news_retriever", return_value=news):
        brief = service.build_brief(
            _settings().model_copy(update={"watchlist": (), "benchmarks": ()}),
            now=_NOW,
        )
    assert [item.title for item in brief.headlines] == [
        "RFC date",
        "Naive UTC date",
        "At cutoff",
        "No date",
        "Unknown date",
    ]
    assert brief.headlines[0].published_at == datetime(
        2026, 9, 25, 14, tzinfo=UTC
    )
    assert brief.headlines[-1].published_at is None
    assert "2 with unknown dates" in brief.sources[0].detail


def test_matching_uses_precise_phrases_and_unambiguous_short_tickers() -> None:
    """Avoid substring and ordinary article matches while accepting aliases."""
    settings = _settings().model_copy(
        update={
            "watchlist": (
                WatchItem(symbol="A", name="Agilent"),
                WatchItem(symbol="CAT", name="Caterpillar"),
                WatchItem(symbol="AAPL", aliases=("Cupertino company",)),
            ),
            "benchmarks": (),
        }
    )
    market = MagicMock(spec=MarketRetriever)
    market.retrieve_range.return_value = []
    news = MagicMock(spec=NewsRetriever)
    news.fetch.return_value = [
        _news("A difficult day for manufacturing education", "general"),
        _news("$A expands its laboratory business", "ticker"),
        _news("Agilent plans a new site", "name"),
        _news("Cupertino company comments on interest rates", "alias"),
        _news("Caterpillar opens a factory", "company"),
        _news("Disinterest rates as concern among readers", "boundary"),
    ]
    with (
        patch.object(service, "create_market_retriever", return_value=market),
        patch.object(service, "create_news_retriever", return_value=news),
    ):
        brief = service.build_brief(settings, now=_NOW)
    by_title = {item.title: item for item in brief.headlines}
    assert by_title["A difficult day for manufacturing education"].symbols == ()
    assert by_title["$A expands its laboratory business"].symbols == ("A",)
    assert by_title["Agilent plans a new site"].symbols == ("A",)
    assert by_title["Caterpillar opens a factory"].symbols == ("CAT",)
    assert by_title["Cupertino company comments on interest rates"].symbols == (
        "AAPL",
    )
    assert by_title["Cupertino company comments on interest rates"].themes == (
        "Rates",
    )
    assert by_title["Disinterest rates as concern among readers"].themes == ()


def test_deduplication_merges_url_title_scope_and_source_provenance() -> None:
    """Merge tracking URLs and normalized titles without losing source labels."""
    settings = _settings().model_copy(
        update={
            "watchlist": (),
            "benchmarks": (),
            "feeds": (
                Feed(
                    name="First",
                    url=HttpUrl("https://example.com/feed-1"),
                    symbols=("AAPL",),
                ),
                Feed(
                    name="Second",
                    url=HttpUrl("https://example.com/feed-2"),
                    symbols=("SPY",),
                ),
            ),
        }
    )
    first = MagicMock(spec=NewsRetriever)
    first.fetch.return_value = [
        _news("Economic release!", "release?utm_source=first&story=7#section")
    ]
    second = MagicMock(spec=NewsRetriever)
    second.fetch.return_value = [
        _news("Updated release title", "release?story=7&utm_medium=second"),
        _news("Economic   RELEASE", "syndicated"),
    ]
    with patch.object(
        service, "create_news_retriever", side_effect=[first, second]
    ):
        brief = service.build_brief(settings, now=_NOW)
    assert len(brief.headlines) == 1
    assert set(brief.headlines[0].symbols) == {"AAPL", "SPY"}
    assert set(brief.headlines[0].source.split(" | ")) == {"First", "Second"}
    assert "utm_" not in str(brief.headlines[0].url)
    assert "#" not in str(brief.headlines[0].url)
    assert sum(item.records for item in brief.sources) == 3


def test_unsafe_article_urls_are_omitted_and_empty_feed_is_explicit() -> None:
    """Reject executable, local-file, credential-bearing, and malformed links."""
    news = MagicMock(spec=NewsRetriever)
    news.fetch.return_value = [
        NewsItem(title="Unsafe", url=url, source="provider")
        for url in (
            "javascript:alert(1)",
            "file:///etc/passwd",
            "https://user:secret@example.com/article",
            "not a url",
        )
    ]
    with patch.object(service, "create_news_retriever", return_value=news):
        brief = service.build_brief(
            _settings().model_copy(update={"watchlist": (), "benchmarks": ()}),
            now=_NOW,
        )
    assert brief.headlines == ()
    assert brief.sources[0].status == "empty"
    assert brief.prompts == (
        "No usable market or headline evidence is available. Inspect source coverage and refresh before drawing conclusions.",
    )


@pytest.mark.parametrize(
    "variant", ["compatible", "demo", "settings", "future", "same-time"]
)
def test_previous_comparison_requires_compatible_earlier_live_snapshot(
    variant: str,
) -> None:
    """Compare headlines only against earlier live snapshots of these settings."""
    settings = _settings().model_copy(
        update={"watchlist": (), "benchmarks": ()}
    )
    previous = _brief(
        settings,
        (
            Headline(
                title="Earlier phrasing",
                url=HttpUrl("https://example.com/shared?utm_source=prior"),
                source="General",
            ),
        ),
    )
    if variant == "demo":
        previous = previous.model_copy(update={"demo": True})
    elif variant == "settings":
        previous = previous.model_copy(
            update={
                "settings": settings.model_copy(update={"goal": "Changed goal"})
            }
        )
    elif variant == "future":
        previous = previous.model_copy(
            update={"generated_at": _NOW + timedelta(days=1)}
        )
    elif variant == "same-time":
        previous = previous.model_copy(update={"generated_at": _NOW})
    news = MagicMock(spec=NewsRetriever)
    news.fetch.return_value = [
        _news("New phrasing", "shared?utm_source=now"),
        _news("Another event", "another"),
    ]
    with patch.object(service, "create_news_retriever", return_value=news):
        brief = service.build_brief(settings, previous=previous, now=_NOW)
    by_title = {item.title: item for item in brief.headlines}
    assert by_title["New phrasing"].is_new is (variant != "compatible")
    assert by_title["Another event"].is_new
    assert brief.previous_brief_id == (
        previous.brief_id if variant == "compatible" else None
    )


def test_prompts_preserve_due_theses_and_avoid_causal_or_trade_claims() -> None:
    """Prompt explicit thesis reviews, observed moves, and matched topic questions."""
    settings = _settings().model_copy(
        update={
            "watchlist": (
                WatchItem(
                    symbol="AAPL",
                    thesis="Margins remain resilient",
                    invalidation="Two quarters of margin contraction",
                    review_on=date(2026, 9, 25),
                ),
            )
        }
    )
    entry = JournalEntry(
        entry_id="b" * 32,
        created_at=_NOW - timedelta(days=10),
        symbol="AAPL",
        observation="Management reported capacity additions",
        invalidation="Utilization falls",
        review_on=date(2026, 9, 26),
    )
    market = MagicMock(spec=MarketRetriever)
    market.retrieve_range.return_value = [_quote(24, 100), _quote(25, 104)]
    news = MagicMock(spec=NewsRetriever)
    news.fetch.return_value = [
        _news("Interest rates decision released", "rates")
    ]
    with (
        patch.object(service, "create_market_retriever", return_value=market),
        patch.object(service, "create_news_retriever", return_value=news),
    ):
        brief = service.build_brief(settings, journal=(entry,), now=_NOW)
    prose = "\n".join(brief.prompts)
    assert "Margins remain resilient" in prose
    assert "Two quarters of margin contraction" in prose
    assert "Utilization falls" in prose
    assert "+4.00%" in prose
    assert "does not establish a cause or a trade signal" in prose
    assert "How have financing assumptions changed?" in prose


def test_demo_is_deterministic_synthetic_and_never_loads_adapters() -> None:
    """Generate reproducible illustrative evidence with no adapter instantiation."""
    with (
        patch.object(
            service,
            "create_market_retriever",
            side_effect=AssertionError("network forbidden"),
        ) as market,
        patch.object(
            service,
            "create_news_retriever",
            side_effect=AssertionError("network forbidden"),
        ) as news,
        patch(
            "sec_nlp.core.market._load_market_module",
            side_effect=AssertionError("native load forbidden"),
        ),
        patch(
            "sec_nlp.core.news.client._load_newswatch_module",
            side_effect=AssertionError("native load forbidden"),
        ),
    ):
        first = service.build_demo_brief(_settings(), now=_NOW)
        second = service.build_demo_brief(_settings(), now=_NOW)
    assert first == second
    assert first.demo
    assert first.previous_brief_id is None
    assert all(item.name.startswith("Synthetic demo") for item in first.sources)
    assert all(
        item.source == "Synthetic demo" and item.url.host == "example.com"
        for item in first.headlines
    )
    assert all(item.source_url.host == "example.com" for item in first.market)
    market.assert_not_called()
    news.assert_not_called()


def test_empty_workspace_does_not_construct_retrievers() -> None:
    """Allow a local workspace without sources or symbols to return an empty brief."""
    settings = InvestingSettings(benchmarks=(), company_feeds=False)
    with (
        patch.object(service, "create_market_retriever") as market,
        patch.object(service, "create_news_retriever") as news,
    ):
        brief = service.build_brief(settings, now=_NOW)
    assert brief.market == ()
    assert brief.headlines == ()
    assert brief.sources == ()
    assert brief.prompts
    market.assert_not_called()
    news.assert_not_called()


def test_report_time_normalizes_aware_offsets_and_rejects_naive_time() -> None:
    """Avoid relying on the machine's local timezone for report cutoffs."""
    offset_time = datetime(2026, 9, 26, 7, tzinfo=timezone(timedelta(hours=-5)))
    assert (
        service.build_demo_brief(_settings(), now=offset_time).generated_at
        == _NOW
    )
    with pytest.raises(ValueError, match="timezone"):
        service.build_brief(_settings(), now=datetime(2026, 9, 26))


def test_company_rss_rate_limit_remains_visible_with_other_evidence() -> None:
    """Keep general headlines and market prices when a company feed is blocked."""
    settings = _settings().model_copy(update={"company_feeds": True})
    market = MagicMock(spec=MarketRetriever)
    market.retrieve_range.return_value = [_quote(25, 200)]
    general = MagicMock(spec=NewsRetriever)
    general.fetch.return_value = [
        _news("General release remains available", "general")
    ]
    company = MagicMock(spec=NewsRetriever)
    company.fetch.side_effect = RuntimeError("HTTP 429 Too Many Requests")
    with (
        patch.object(service, "create_market_retriever", return_value=market),
        patch.object(
            service, "create_news_retriever", side_effect=[general, company]
        ),
    ):
        brief = service.build_brief(settings, now=_NOW)
    assert len(brief.headlines) == 1
    assert all(item.close == 200 for item in brief.market)
    failure = brief.sources[-1]
    assert failure.name == "Yahoo Finance: AAPL"
    assert failure.kind == "news"
    assert failure.status == "error"
    assert "429" in failure.detail
    assert brief.sources[-2].status == "ok"


def test_common_word_tickers_require_exact_uppercase_tokens() -> None:
    """Avoid deriving stock relevance from ordinary common words in headlines."""
    settings = _settings().model_copy(
        update={
            "watchlist": tuple(
                WatchItem(symbol=symbol)
                for symbol in ("NOW", "ALL", "WELL", "COST", "CAT", "IT", "ON")
            ),
            "benchmarks": (),
        }
    )
    market = MagicMock(spec=MarketRetriever)
    market.retrieve_range.return_value = []
    news = MagicMock(spec=NewsRetriever)
    news.fetch.return_value = [
        _news(
            "Now all consumers weigh cost: is it well spent on cat food?",
            "ordinary",
        ),
        _news("NOW and COST release quarterly updates", "tickers"),
    ]
    with (
        patch.object(service, "create_market_retriever", return_value=market),
        patch.object(service, "create_news_retriever", return_value=news),
    ):
        brief = service.build_brief(settings, now=_NOW)
    by_title = {item.title: item for item in brief.headlines}
    assert (
        by_title[
            "Now all consumers weigh cost: is it well spent on cat food?"
        ].symbols
        == ()
    )
    assert by_title["NOW and COST release quarterly updates"].symbols == (
        "NOW",
        "COST",
    )


def test_recurring_headline_titles_keep_distinct_publication_dates() -> None:
    """Retain separate policy releases while merging same-day syndication."""
    settings = _settings().model_copy(
        update={"watchlist": (), "benchmarks": (), "lookback_days": 90}
    )
    news = MagicMock(spec=NewsRetriever)
    news.fetch.return_value = [
        _news(
            "Federal Reserve issues FOMC statement",
            "january-release",
            published="2026-01-28T19:00:00Z",
        ),
        _news(
            "Federal Reserve issues FOMC statement",
            "march-release",
            published="2026-03-18T18:00:00Z",
        ),
        _news(
            "Federal Reserve issues FOMC statement!",
            "march-syndication",
            published="2026-03-19T02:00:00+08:00",
        ),
    ]
    with patch.object(service, "create_news_retriever", return_value=news):
        brief = service.build_brief(
            settings, now=datetime(2026, 3, 19, 12, tzinfo=UTC)
        )
    assert len(brief.headlines) == 2
    assert {
        item.published_at.date()
        for item in brief.headlines
        if item.published_at is not None
    } == {date(2026, 1, 28), date(2026, 3, 18)}


def test_previous_title_comparison_qualifies_normalized_publication_date() -> (
    None
):
    """Mark recurring releases as new and same-day syndicated releases as seen."""
    settings = _settings().model_copy(
        update={"watchlist": (), "benchmarks": (), "lookback_days": 90}
    )
    previous = Brief(
        brief_id="a" * 32,
        generated_at=datetime(2026, 1, 29, 12, tzinfo=UTC),
        settings=settings,
        headlines=(
            Headline(
                title="Federal Reserve issues FOMC statement",
                url=HttpUrl("https://example.com/previous-release"),
                source="General",
                published_at=datetime(
                    2026, 1, 29, 3, tzinfo=timezone(timedelta(hours=8))
                ),
            ),
        ),
    )
    news = MagicMock(spec=NewsRetriever)
    news.fetch.return_value = [
        _news(
            "Federal Reserve issues FOMC statement",
            "january-syndication",
            published="2026-01-28T19:00:00Z",
        ),
        _news(
            "Federal Reserve issues FOMC statement",
            "march-release",
            published="2026-03-18T18:00:00Z",
        ),
    ]
    with patch.object(service, "create_news_retriever", return_value=news):
        brief = service.build_brief(
            settings,
            previous=previous,
            now=datetime(2026, 3, 19, 12, tzinfo=UTC),
        )
    assert len(brief.headlines) == 2
    assert brief.headlines[0].is_new
    assert not brief.headlines[1].is_new
    assert brief.previous_brief_id == previous.brief_id


def test_undated_titles_do_not_merge_distinct_articles_or_mark_them_seen() -> (
    None
):
    """Require URL identity when the publication date is unknown."""
    settings = _settings().model_copy(
        update={"watchlist": (), "benchmarks": ()}
    )
    previous = _brief(
        settings,
        (
            Headline(
                title="Recurring release",
                url=HttpUrl("https://example.com/earlier-undated"),
                source="General",
            ),
        ),
    )
    news = MagicMock(spec=NewsRetriever)
    news.fetch.return_value = [
        _news("Recurring release", "first-undated", published=None),
        _news("Recurring release", "second-undated", published=None),
        _news(
            "Recurring release",
            "earlier-undated?utm_source=again",
            published=None,
        ),
        _news(
            "Recurring release",
            "first-undated?utm_source=duplicate",
            published=None,
        ),
    ]
    with patch.object(service, "create_news_retriever", return_value=news):
        brief = service.build_brief(settings, previous=previous, now=_NOW)
    assert len(brief.headlines) == 3
    assert sum(item.is_new for item in brief.headlines) == 2
    assert all(item.published_at is None for item in brief.headlines)


def test_two_letter_tickers_need_explicit_context_or_company_aliases() -> None:
    """Avoid treating generic AI and IT reporting as company-specific evidence."""
    settings = _settings().model_copy(
        update={
            "watchlist": (
                WatchItem(symbol="AI", name="C3.ai"),
                WatchItem(symbol="IT", name="Gartner"),
            ),
            "benchmarks": (),
        }
    )
    market = MagicMock(spec=MarketRetriever)
    market.retrieve_range.return_value = []
    news = MagicMock(spec=NewsRetriever)
    news.fetch.return_value = [
        _news("AI investment lifts IT sector spending", "sector"),
        _news("$AI and (IT) release quarterly updates", "cashtags"),
        _news("NYSE: AI expands while NYSE:IT presents research", "exchange"),
        _news("C3.ai and Gartner issue announcements", "names"),
    ]
    with (
        patch.object(service, "create_market_retriever", return_value=market),
        patch.object(service, "create_news_retriever", return_value=news),
    ):
        brief = service.build_brief(settings, now=_NOW)
    by_title = {item.title: item for item in brief.headlines}
    assert by_title["AI investment lifts IT sector spending"].symbols == ()
    assert all(
        item.symbols == ("AI", "IT")
        for item in brief.headlines
        if item.title != "AI investment lifts IT sector spending"
    )
