# src/sec_nlp/app/investing/service.py
"""Build investing briefs from independently retrieved market and news evidence.

This service reuses the optional market and newswatch adapters without entering
filing pipelines, resolving SEC aliases, or calling a model. Date normalization,
headline matching, and review prompts remain deterministic and expose missing
coverage. Synthetic demonstration records never invoke either adapter.
"""

import logging
import math
import re
from datetime import UTC, date, datetime, timedelta
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
from pydantic import HttpUrl

from sec_nlp.app.investing.models import (
    Brief,
    Feed,
    Headline,
    InvestingSettings,
    JournalEntry,
    MarketObservation,
    SourceStatus,
)
from sec_nlp.core.market import MarketQuote, create_market_retriever
from sec_nlp.core.news.client import NewsItem, create_news_retriever
from sec_nlp.core.news.normalization import (
    parse_timestamp as _parse_timestamp,
    safe_url as _safe_url,
    title_key as _title_key,
    url_key as _url_key,
)

logger = logging.getLogger(__name__)
_NEWS_LIMIT = 500


def _utc_now(now: datetime | None) -> datetime:
    """Return an aware UTC report time, rejecting ambiguous local timestamps."""
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone")
    return now.astimezone(UTC)


def _symbols(settings: InvestingSettings) -> tuple[str, ...]:
    """Return watched and reference symbols once in configured order."""
    return tuple(
        dict.fromkeys(
            (
                *[item.symbol for item in settings.watchlist],
                *settings.benchmarks,
            )
        )
    )


def _market_url(symbol: str) -> HttpUrl:
    """Return the provider's asset page with the symbol safely encoded."""
    return HttpUrl(f"https://finance.yahoo.com/quote/{quote(symbol, safe='')}/")


def _error_detail(error: BaseException) -> str:
    """Return a bounded explanation suitable for a source availability report."""
    return f"{type(error).__name__}: {error}"[:400]


def _valid_quotes(
    quotes: list[MarketQuote], start_date: date, now: datetime
) -> list[MarketQuote]:
    """Select finite, dated quotes and keep the latest quote per UTC session."""
    sessions: dict[date, MarketQuote] = {}
    for item in quotes:
        try:
            timestamp = datetime.fromtimestamp(item.timestamp, UTC)
        except (ValueError, OverflowError, OSError):
            logger.debug("Ignoring invalid market timestamp", exc_info=True)
            continue
        if timestamp > now or timestamp.date() < start_date:
            continue
        prices = (
            item.open_price,
            item.high,
            item.low,
            item.close,
            item.adjclose,
        )
        if (
            not all(math.isfinite(price) and price > 0 for price in prices)
            or item.volume < 0
            or item.low > min(item.open_price, item.close)
            or item.high < max(item.open_price, item.close)
        ):
            continue
        session = timestamp.date()
        previous = sessions.get(session)
        if previous is None or item.timestamp >= previous.timestamp:
            sessions[session] = item
    return [sessions[session] for session in sorted(sessions)]


def _change(quotes: list[MarketQuote], sessions: int) -> float | None:
    """Return adjusted-close change only when the requested history exists."""
    if len(quotes) <= sessions:
        return None
    result = (quotes[-1].adjclose / quotes[-sessions - 1].adjclose - 1) * 100
    return result if math.isfinite(result) else None


def _fetch_market(
    settings: InvestingSettings, now: datetime
) -> tuple[tuple[MarketObservation, ...], tuple[SourceStatus, ...]]:
    """Fetch each unique symbol independently and report missing history."""
    symbols = _symbols(settings)
    if not symbols:
        return (), ()
    try:
        retriever = create_market_retriever()
    except (
        ImportError,
        RuntimeError,
        ValueError,
        OSError,
        TypeError,
        AttributeError,
    ) as error:
        logger.debug("Market adapter setup failed", exc_info=True)
        return (
            tuple(
                MarketObservation(symbol=symbol, source_url=_market_url(symbol))
                for symbol in symbols
            ),
            tuple(
                SourceStatus(
                    name=symbol,
                    kind="market",
                    status="error",
                    detail=_error_detail(error),
                )
                for symbol in symbols
            ),
        )
    start_date = now.date() - timedelta(days=settings.market_days)
    observations: list[MarketObservation] = []
    statuses: list[SourceStatus] = []
    for symbol in symbols:
        try:
            raw = retriever.retrieve_range(
                symbol, (start_date, now.date() + timedelta(days=1))
            )
            quotes = _valid_quotes(raw, start_date, now)
        except (
            RuntimeError,
            ValueError,
            OSError,
            TypeError,
            KeyError,
            AttributeError,
            OverflowError,
        ) as error:
            logger.debug(
                "Market retrieval failed for %s", symbol, exc_info=True
            )
            observations.append(
                MarketObservation(symbol=symbol, source_url=_market_url(symbol))
            )
            statuses.append(
                SourceStatus(
                    name=symbol,
                    kind="market",
                    status="error",
                    detail=_error_detail(error),
                )
            )
            continue
        if not quotes:
            observations.append(
                MarketObservation(symbol=symbol, source_url=_market_url(symbol))
            )
            statuses.append(
                SourceStatus(
                    name=symbol,
                    kind="market",
                    status="empty",
                    detail=f"No usable quotes in the requested window; {len(raw)} returned.",
                )
            )
            continue
        latest = quotes[-1]
        quote_date = datetime.fromtimestamp(latest.timestamp, UTC).date()
        age = (now.date() - quote_date).days
        stale = age > settings.stale_after_days
        observations.append(
            MarketObservation(
                symbol=symbol,
                quote_date=quote_date,
                close=latest.close,
                change_1d_pct=_change(quotes, 1),
                change_5d_pct=_change(quotes, 5),
                observations=len(quotes),
                stale=stale,
                source_url=_market_url(symbol),
            )
        )
        detail = f"{len(quotes)} usable UTC sessions; {len(raw) - len(quotes)} invalid, outside-window, future, or duplicate records omitted."
        if len(quotes) < 6:
            detail += " Five-session change needs at least six sessions."
        if stale:
            detail += f" Latest quote is stale ({age} calendar days old)."
        statuses.append(
            SourceStatus(
                name=symbol,
                kind="market",
                status="ok",
                records=len(quotes),
                detail=detail,
            )
        )
    return tuple(observations), tuple(statuses)


def _dated_title_key(headline: Headline) -> str | None:
    """Identify a dated headline without conflating recurring release titles.

    Unknown dates supply no title identity because similarly named articles
    cannot be established as duplicates without a shared date or URL.
    """
    if headline.published_at is None:
        return None
    title = _title_key(headline.title)
    if not title:
        return None
    published_date = headline.published_at.astimezone(UTC).date()
    return f"{published_date.isoformat()}:{title}"


def _phrase_matches(text: str, phrase: str, *, ticker: bool = False) -> bool:
    """Match uppercase tickers or case-insensitive company and topic phrases.

    Tickers of one or two letters require a cashtag, parentheses, or exchange
    label to distinguish them from articles, pronouns, and sector initials.
    Longer tickers remain case-sensitive to avoid ordinary common words.
    """
    cleaned = " ".join(phrase.split())
    if not cleaned:
        return False
    pattern = (
        r"(?<!\w)"
        + r"\s+".join(re.escape(part) for part in cleaned.split())
        + r"(?!\w)"
    )
    if ticker and len(cleaned) <= 2:
        pattern = (
            r"(?:\$"
            + re.escape(cleaned)
            + r"(?!\w)|\("
            + re.escape(cleaned)
            + r"\)|(?<!\w)(?:NYSE|NASDAQ|AMEX):\s*"
            + re.escape(cleaned)
            + r"(?!\w))"
        )
    flags = 0 if ticker else re.IGNORECASE
    return re.search(pattern, text, flags) is not None


def _headline(
    item: NewsItem, feed: Feed, settings: InvestingSettings, now: datetime
) -> Headline | None:
    """Normalize one headline and attach phrase and explicit-source labels."""
    title = " ".join(item.title.split())
    url = _safe_url(item.url)
    if not title or url is None:
        return None
    published = _parse_timestamp(item.published_at)
    if (
        published is not None
        and not now - timedelta(days=settings.lookback_days) <= published <= now
    ):
        return None
    symbols = list(feed.symbols)
    for watched in settings.watchlist:
        if watched.symbol not in symbols and (
            _phrase_matches(title, watched.symbol, ticker=True)
            or any(
                _phrase_matches(title, phrase)
                for phrase in (watched.name, *watched.aliases)
            )
        ):
            symbols.append(watched.symbol)
    themes = tuple(
        theme.name
        for theme in settings.themes
        if any(_phrase_matches(title, keyword) for keyword in theme.keywords)
    )
    return Headline(
        title=title,
        url=url,
        source=feed.name,
        published_at=published,
        symbols=tuple(symbols),
        themes=themes,
    )


def _feeds(settings: InvestingSettings) -> tuple[Feed, ...]:
    """Combine general sources with explicitly scoped Yahoo company feeds.

    Yahoo may rate-limit or disable an RSS response. The normal independent
    retrieval path reports that company feed error in the brief and retains
    evidence from every other successful source.
    """
    configured = list(settings.feeds)
    names = {feed.name.casefold() for feed in configured}
    if settings.company_feeds:
        for watched in settings.watchlist:
            endpoint = HttpUrl(
                f"https://finance.yahoo.com/rss/headline?s={quote(watched.symbol, safe='')}"
            )
            name = f"Yahoo Finance: {watched.symbol}"
            while name.casefold() in names:
                name += " (company)"
            configured.append(
                Feed(name=name, url=endpoint, symbols=(watched.symbol,))
            )
            names.add(name.casefold())
    return tuple(configured)


def _fetch_news(
    settings: InvestingSettings, now: datetime
) -> tuple[list[Headline], tuple[SourceStatus, ...]]:
    """Retrieve every feed separately so one failure cannot erase other evidence."""
    headlines: list[Headline] = []
    statuses: list[SourceStatus] = []
    for feed in _feeds(settings):
        try:
            retriever = create_news_retriever(
                user_agent=settings.user_agent,
                feeds=[(str(feed.url), feed.feed_type, feed.name)],
            )
            raw = retriever.fetch(keywords=[], max_results=_NEWS_LIMIT)
            usable = [
                headline
                for item in raw[:_NEWS_LIMIT]
                if (headline := _headline(item, feed, settings, now))
                is not None
            ]
        except (
            ImportError,
            RuntimeError,
            ValueError,
            OSError,
            TypeError,
            KeyError,
            AttributeError,
            OverflowError,
            httpx.HTTPError,
        ) as error:
            logger.debug(
                "News retrieval failed for %s", feed.name, exc_info=True
            )
            statuses.append(
                SourceStatus(
                    name=feed.name,
                    kind="news",
                    status="error",
                    detail=_error_detail(error),
                )
            )
            continue
        headlines.extend(usable)
        undated = sum(item.published_at is None for item in usable)
        detail = f"{len(usable)} usable headlines before cross-source deduplication; {undated} with unknown dates. Requested up to {_NEWS_LIMIT} source records; feeds may retain less history."
        statuses.append(
            SourceStatus(
                name=feed.name,
                kind="news",
                status="ok" if usable else "empty",
                records=len(usable),
                detail=detail,
            )
        )
    return headlines, tuple(statuses)


def _merge_headlines(first: Headline, second: Headline) -> Headline:
    """Preserve combined relevance and provenance when two headlines duplicate."""
    return Headline(
        title=first.title,
        url=first.url,
        source=" | ".join(
            dict.fromkeys(
                (*first.source.split(" | "), *second.source.split(" | "))
            )
        ),
        published_at=first.published_at or second.published_at,
        symbols=tuple(dict.fromkeys((*first.symbols, *second.symbols))),
        themes=tuple(dict.fromkeys((*first.themes, *second.themes))),
        is_new=first.is_new and second.is_new,
    )


def _deduplicate(
    headlines: list[Headline], previous: Brief | None
) -> list[Headline]:
    """Merge matching URLs or same-UTC-date titles across duplicate groups."""
    prior_urls = (
        {_url_key(item.url) for item in previous.headlines}
        if previous
        else set()
    )
    prior_titles = (
        {
            key
            for item in previous.headlines
            if (key := _dated_title_key(item)) is not None
        }
        if previous
        else set()
    )
    groups: dict[int, Headline] = {}
    identities: dict[tuple[str, str], int] = {}
    minimum = datetime.min.replace(tzinfo=UTC)
    ordered = sorted(
        headlines,
        key=lambda item: (
            -(item.published_at or minimum).timestamp(),
            item.title.casefold(),
            str(item.url),
        ),
    )
    for sequence, item in enumerate(ordered):
        url_key = _url_key(item.url)
        title_key = _dated_title_key(item)
        item = item.model_copy(
            update={
                "is_new": url_key not in prior_urls
                and title_key not in prior_titles
            }
        )
        keys = (("url", url_key),)
        if title_key is not None:
            keys = (*keys, ("title", title_key))
        matches = {identities[key] for key in keys if key in identities}
        group = min(matches) if matches else sequence
        for matched in sorted(matches, reverse=True):
            item = _merge_headlines(groups.pop(matched), item)
        groups[group] = item
        if matches:
            identities = {
                key: group if value in matches else value
                for key, value in identities.items()
            }
        for key in keys:
            identities[key] = group
    return sorted(
        groups.values(),
        key=lambda item: (
            -(item.published_at or minimum).timestamp(),
            item.title.casefold(),
            str(item.url),
        ),
    )


def _prompts(
    settings: InvestingSettings,
    market: tuple[MarketObservation, ...],
    headlines: tuple[Headline, ...],
    journal: tuple[JournalEntry, ...],
    now: datetime,
) -> tuple[str, ...]:
    """Turn dated reviews and observed evidence into bounded research questions."""
    prompts: list[str] = []
    for watched in settings.watchlist:
        if watched.review_on is not None and watched.review_on <= now.date():
            check = (
                watched.invalidation
                or "What evidence would challenge the current thesis?"
            )
            prompts.append(
                f"Review {watched.symbol} thesis (due {watched.review_on.isoformat()}): {watched.thesis or 'Write the hypothesis you want to test.'} Invalidation check: {check}"
            )
    for entry in journal:
        if (
            entry.created_at <= now
            and entry.review_on is not None
            and entry.review_on <= now.date()
        ):
            prompts.append(
                f"Review journal {entry.entry_id[:8]}{f' ({entry.symbol})' if entry.symbol else ''} (due {entry.review_on.isoformat()}): {entry.observation} Check: {entry.invalidation or 'What new evidence supports or challenges this observation?'}"
            )
    for observation in market:
        change = observation.change_1d_pct
        if change is not None and abs(change) >= settings.move_threshold_pct:
            prompts.append(
                f"Research {observation.symbol}'s observed {change:+.2f}% adjusted-close move over one available session ending {observation.quote_date}{' (stale quote)' if observation.stale else ''}. Compare dated primary sources and the thesis; price movement alone does not establish a cause or a trade signal."
            )
    matched_themes = {
        theme for headline in headlines for theme in headline.themes
    }
    for theme in settings.themes:
        if theme.name in matched_themes:
            prompts.append(
                f"{theme.name}: {theme.question or 'What changed, and which primary evidence supports it?'} Headline matching indicates a topic to investigate, not causation."
            )
    if not headlines and not any(item.close is not None for item in market):
        prompts.append(
            "No usable market or headline evidence is available. Inspect source coverage and refresh before drawing conclusions."
        )
    return tuple(prompts)


def build_brief(
    settings: InvestingSettings,
    *,
    journal: tuple[JournalEntry, ...] = (),
    previous: Brief | None = None,
    now: datetime | None = None,
    include_market: bool = True,
    include_news: bool = True,
) -> Brief:
    """Build a current-events and investing report with explicit source coverage.

    Args:
        settings: Immutable watchlist, themes, source definitions, and windows.
        journal: User-authored research entries to preserve with this snapshot.
        previous: Optional earlier live brief with identical settings for comparison.
        now: Aware report time; defaults to the current UTC time.
        include_market: Whether to retrieve market observations.
        include_news: Whether to retrieve configured headlines.

    Returns:
        An immutable brief containing available evidence, individual source errors,
        and research prompts. Missing history never becomes a zero return.

    Raises:
        ValueError: If now does not include a timezone.
    """
    generated_at = _utc_now(now)
    compatible = (
        previous
        if previous is not None
        and not previous.demo
        and previous.settings == settings
        and previous.generated_at < generated_at
        else None
    )
    market, market_statuses = (
        _fetch_market(settings, generated_at) if include_market else ((), ())
    )
    news, news_statuses = (
        _fetch_news(settings, generated_at) if include_news else ([], ())
    )
    headlines = tuple(_deduplicate(news, compatible)[: settings.max_headlines])
    return Brief(
        brief_id=uuid4().hex,
        generated_at=generated_at,
        settings=settings,
        previous_brief_id=compatible.brief_id
        if compatible is not None
        else None,
        market=market,
        headlines=headlines,
        sources=(*market_statuses, *news_statuses),
        journal=journal,
        prompts=_prompts(settings, market, headlines, journal, generated_at),
    )


def build_demo_brief(
    settings: InvestingSettings,
    *,
    journal: tuple[JournalEntry, ...] = (),
    now: datetime | None = None,
) -> Brief:
    """Build clearly labeled synthetic evidence without retrieving any data.

    Args:
        settings: Watchlist and themes used to illustrate a research workspace.
        journal: User-authored entries to include alongside the synthetic evidence.
        now: Aware report time; identical settings and time produce identical output.

    Returns:
        A demo brief with example.com article links and synthetic source labels.

    Raises:
        ValueError: If now does not include a timezone.
    """
    generated_at = _utc_now(now)
    session = generated_at.date()
    while session.weekday() >= 5:
        session -= timedelta(days=1)
    market = tuple(
        MarketObservation(
            symbol=symbol,
            quote_date=session,
            close=round(100 + index * 17.5, 2),
            change_1d_pct=3.5 if index == 0 else -0.75,
            change_5d_pct=5.25 if index == 0 else 1.25,
            observations=6,
            source_url=HttpUrl(
                f"https://example.com/synthetic-market/{quote(symbol, safe='')}"
            ),
        )
        for index, symbol in enumerate(_symbols(settings))
    )
    examples: list[Headline] = [
        Headline(
            title="Synthetic example: economic release prompts a review of growth assumptions",
            url=HttpUrl("https://example.com/synthetic-news/economic-release"),
            source="Synthetic demo",
            published_at=generated_at - timedelta(hours=2),
        )
    ]
    for index, watched in enumerate(settings.watchlist):
        examples.append(
            Headline(
                title=f"Synthetic example: {watched.name or watched.symbol} outlines an operating update",
                url=HttpUrl(
                    f"https://example.com/synthetic-news/company-{index}"
                ),
                source="Synthetic demo",
                published_at=generated_at - timedelta(hours=index + 3),
                symbols=(watched.symbol,),
            )
        )
    for index, theme in enumerate(settings.themes):
        examples.append(
            Headline(
                title=f"Synthetic example: a new development in {theme.name}",
                url=HttpUrl(
                    f"https://example.com/synthetic-news/theme-{index}"
                ),
                source="Synthetic demo",
                published_at=generated_at - timedelta(hours=index + 1),
                themes=(theme.name,),
            )
        )
    headlines = tuple(_deduplicate(examples, None)[: settings.max_headlines])
    sources = tuple(
        SourceStatus(
            name=f"Synthetic demo: {item.symbol}",
            kind="market",
            status="ok",
            records=item.observations,
            detail="Fabricated illustration; not a current market quote.",
        )
        for item in market
    )
    return Brief(
        brief_id=uuid5(
            NAMESPACE_URL,
            f"sec-nlp-demo:{settings.model_dump_json()}:{generated_at.isoformat()}:{','.join(entry.entry_id for entry in journal)}",
        ).hex,
        generated_at=generated_at,
        settings=settings,
        demo=True,
        market=market,
        headlines=headlines,
        sources=(
            *sources,
            SourceStatus(
                name="Synthetic demo",
                kind="news",
                status="ok",
                records=len(headlines),
                detail="Fabricated example.com articles; no sources were contacted.",
            ),
        ),
        journal=journal,
        prompts=_prompts(settings, market, headlines, journal, generated_at),
    )
