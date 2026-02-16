"""Headline fetch helpers backed by the newswatch Rust extension."""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.news.client import create_news_retriever

from ..config import NewsSettings
from ..models import NewsHeadline

FeedTuple = tuple[str, str, str]


def _infer_feed_type(url: str) -> str:
    lowered = url.lower()
    if "newsapi" in lowered or "polygon" in lowered or "json" in lowered:
        return "json_api"
    return "rss"


def _normalize_feed_type(raw_type: str) -> str:
    lowered = raw_type.strip().lower()
    if lowered in {"json", "json_api", "api"}:
        return "json_api"
    return "rss"


def _default_feed_name(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "custom-feed"


def parse_feed_specs(feed_specs: list[str]) -> list[FeedTuple]:
    """Parse feed CLI values into `(url, feed_type, name)` tuples."""
    parsed: list[FeedTuple] = []
    seen_urls: set[str] = set()

    for raw_spec in feed_specs:
        spec = raw_spec.strip()
        if not spec:
            continue

        if "|" in spec:
            parts = [part.strip() for part in spec.split("|", maxsplit=2)]
            while len(parts) < 3:
                parts.append("")
            url, feed_type, name = parts
        else:
            url = spec
            feed_type = _infer_feed_type(url)
            name = ""

        if not url or url in seen_urls:
            continue

        seen_urls.add(url)
        normalized_type = _normalize_feed_type(feed_type)
        feed_name = name or _default_feed_name(url)
        parsed.append((url, normalized_type, feed_name))

    return parsed


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None

    try:
        return datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    except ValueError:
        pass

    try:
        return parsedate_to_datetime(stripped)
    except (TypeError, ValueError):
        return None


def _normalize_topics(topics: list[str]) -> list[str]:
    normalized: list[str] = []
    for topic in topics:
        cleaned = topic.strip()
        if cleaned:
            normalized.append(cleaned)
    return list(dict.fromkeys(normalized))


def _default_keywords(symbol: str, topics: list[str]) -> list[str]:
    base = [symbol.strip().upper()]
    base.extend(_normalize_topics(topics))
    return list(dict.fromkeys(item for item in base if item))


def fetch_news_items(
    *,
    symbol: str,
    settings: NewsSettings,
) -> list[NewsHeadline]:
    """Fetch and normalize headlines for a symbol."""

    keywords = _default_keywords(symbol, settings.topics)
    feed_tuples = parse_feed_specs(settings.feeds)

    retriever = create_news_retriever(
        user_agent=f"SEC NLP Tool ({settings.email})",
        feeds=feed_tuples or None,
        rate_limit_secs=settings.rate_limit_secs,
    )

    start_date, end_date = settings.effective_news_date_range
    raw_items = retriever.fetch(keywords, max_results=settings.max_results)

    headlines: list[NewsHeadline] = []
    for item in raw_items:
        published_dt = _parse_timestamp(item.published_at)
        if published_dt is not None:
            published_utc = published_dt.astimezone(UTC)
            published_date = published_utc.date()
            if published_date < start_date or published_date > end_date:
                continue
            published_at = published_utc.isoformat()
            published_date_text = published_date.isoformat()
        else:
            published_at = item.published_at
            published_date_text = None

        headlines.append(
            NewsHeadline(
                symbol=symbol,
                title=item.title.strip(),
                url=item.url,
                source=item.source,
                published_at=published_at,
                published_date=published_date_text,
                snippet=item.snippet,
                matched_keywords=list(dict.fromkeys(item.matched_keywords)),
            )
        )

    headlines.sort(
        key=lambda current: (
            current.published_at or "",
            current.title.lower(),
        ),
        reverse=True,
    )

    logger.debug(
        "Fetched %d headlines for %s (%d kept in date window)",
        len(raw_items),
        symbol,
        len(headlines),
    )

    return headlines
