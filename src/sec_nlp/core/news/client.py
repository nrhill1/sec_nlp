# src/sec_nlp/core/news/client.py
"""Thin wrapper around the Rust ``newswatch`` extension for headline retrieval."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import lru_cache
from importlib import import_module
from types import ModuleType
from urllib.parse import urlsplit
from xml.etree import ElementTree

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.edgar.transport import fetch_sec_bytes
from sec_nlp.core.news.normalization import (
    dated_title_key,
    parse_timestamp,
    safe_url,
    url_key,
)

logger = logging.getLogger(__name__)

type FeedTuple = tuple[str, str, str]
type FeedConfigKey = tuple[FeedTuple, ...]


class NewswatchExtensionError(RuntimeError):
    """Raised when the Rust `newswatch` extension is unavailable."""


class NewsItem(BaseModel):
    """Normalized news item returned by the wrapper."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    url: str
    source: str
    published_at: str | None = None
    matched_keywords: list[str] = Field(default_factory=list)
    snippet: str | None = None


@lru_cache(maxsize=1)
def _load_newswatch_module() -> ModuleType:
    """Load the optional native newswatch extension module."""
    try:
        return import_module("newswatch")
    except (
        ImportError
    ) as exc:  # pragma: no cover - depends on extension install
        raise NewswatchExtensionError(
            "newswatch extension is not available; build it with "
            "`make rs-nw-dev` or `make build-ext`."
        ) from exc


def _field(raw_item, name: str):
    """Read a string-key field from a mapping payload."""
    if isinstance(raw_item, Mapping):
        return raw_item.get(name)
    return getattr(raw_item, name, None)


def _coerce_str(value) -> str | None:
    """Coerce scalar values to strings when possible."""
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return str(value)


def _coerce_keywords(value) -> list[str]:
    """Normalize keyword payloads to a list of strings."""
    if not isinstance(value, list):
        return []
    keywords: list[str] = []
    for item in value:
        text = _coerce_str(item)
        if text is not None:
            keywords.append(text)
    return keywords


def _to_news_item(raw_item) -> NewsItem:
    """Convert one native payload item to a NewsItem model."""
    title = _coerce_str(_field(raw_item, "title")) or ""
    url = _coerce_str(_field(raw_item, "url")) or ""
    source = _coerce_str(_field(raw_item, "source")) or ""
    return NewsItem(
        title=title,
        url=url,
        source=source,
        published_at=_coerce_str(_field(raw_item, "published_at")),
        matched_keywords=_coerce_keywords(_field(raw_item, "matched_keywords")),
        snippet=_coerce_str(_field(raw_item, "snippet")),
    )


def _to_news_items(raw_items: list) -> list[NewsItem]:
    """Convert native payload lists to NewsItem models."""
    return normalize_news_items(
        [_to_news_item(raw_item) for raw_item in raw_items]
    )


def normalize_news_items(items: list[NewsItem]) -> list[NewsItem]:
    """Return safe, chronologically sorted articles with conservative identities.

    Unknown publication dates are retained. Same-title releases on different
    days remain distinct; same-day syndication shares one article identity.

    Args:
        items: Source headlines, including their original publication strings.

    Returns:
        Validated URLs and date-qualified distinct headlines, latest first.
    """
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    accepted: list[tuple[datetime | None, NewsItem]] = []
    for item in items:
        article_url = safe_url(item.url)
        if article_url is None or not item.title.strip():
            continue
        published = parse_timestamp(item.published_at)
        identity = url_key(article_url)
        title_identity = dated_title_key(item.title, published)
        if identity in seen_urls or (
            title_identity is not None and title_identity in seen_titles
        ):
            continue
        seen_urls.add(identity)
        if title_identity is not None:
            seen_titles.add(title_identity)
        accepted.append(
            (
                published,
                item.model_copy(
                    update={
                        "url": str(article_url),
                        "published_at": published.isoformat()
                        if published
                        else None,
                    }
                ),
            )
        )
    accepted.sort(
        key=lambda pair: pair[0] or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return [item for _, item in accepted]


def _sec_rss_items(content: bytes, source: str) -> list[NewsItem]:
    """Parse SEC news RSS without giving its requests a second rate budget."""
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise ValueError("Invalid SEC news feed XML") from exc
    namespace = "{http://www.w3.org/2005/Atom}"
    if root.tag == "rss":
        return [
            NewsItem(
                title=entry.findtext("title", ""),
                url=entry.findtext("link", ""),
                source=source,
                published_at=entry.findtext("pubDate"),
                snippet=entry.findtext("description"),
            )
            for entry in root.findall("./channel/item")
        ]
    if root.tag == namespace + "feed":
        items: list[NewsItem] = []
        for entry in root.findall(namespace + "entry"):
            link = next(
                (
                    node.attrib.get("href", "")
                    for node in entry.findall(namespace + "link")
                    if node.attrib.get("rel", "alternate") == "alternate"
                ),
                "",
            )
            items.append(
                NewsItem(
                    title=entry.findtext(namespace + "title", ""),
                    url=link,
                    source=source,
                    published_at=entry.findtext(namespace + "published")
                    or entry.findtext(namespace + "updated"),
                )
            )
        return items
    raise ValueError("Expected an SEC news RSS or Atom feed")


def _normalize_feeds(feeds: list[FeedTuple]) -> FeedConfigKey:
    """Return immutable feed tuples for cache-key generation."""
    return tuple(
        (str(url), str(feed_type), str(name)) for url, feed_type, name in feeds
    )


class NewsRetriever:
    """Python adapter around `newswatch.NewsClient`."""

    def __init__(
        self,
        feeds: list[tuple[str, str, str]],
        user_agent: str,
        *,
        rate_limit_secs: float = 0.0,
        module: ModuleType | None = None,
    ) -> None:
        """Initialize the newswatch client wrapper."""
        if not feeds:
            raise ValueError("feeds must be non-empty")
        self._sec_feeds = [
            feed
            for feed in feeds
            if (urlsplit(feed[0]).hostname or "").removeprefix("www.")
            == "sec.gov"
            or (urlsplit(feed[0]).hostname or "").endswith(".sec.gov")
        ]
        self._user_agent = user_agent
        native_feeds = [feed for feed in feeds if feed not in self._sec_feeds]
        self._client = None
        if native_feeds:
            native_module = module or _load_newswatch_module()
            self._client = native_module.NewsClient(
                native_feeds, user_agent, float(rate_limit_secs)
            )

    def fetch(
        self,
        keywords: list[str],
        max_results: int = 100,
    ) -> list[NewsItem]:
        """Fetch headlines for the provided keywords."""
        items: list[NewsItem] = []
        if self._client is not None:
            raw_items = self._client.fetch(
                list(keywords), max(500, int(max_results))
            )
            items.extend(_to_news_item(item) for item in raw_items)
        for url, feed_type, name in self._sec_feeds:
            if feed_type not in {"rss", "atom"}:
                raise ValueError("SEC news feeds must use RSS or Atom")
            items.extend(
                _sec_rss_items(fetch_sec_bytes(url, self._user_agent), name)
            )
        if keywords:
            items = [
                item
                for item in items
                if any(
                    keyword.casefold()
                    in f"{item.title} {item.snippet or ''}".casefold()
                    for keyword in keywords
                )
            ]
        return (
            normalize_news_items(items)[:max_results]
            if max_results > 0
            else normalize_news_items(items)
        )


_DEFAULT_RSS_FEEDS: tuple[tuple[str, str, str], ...] = (
    (
        "https://www.sec.gov/news/pressreleases.rss",
        "rss",
        "SEC Press Releases",
    ),
    (
        "https://www.prnewswire.com/rss/financial-services-latest-news/"
        "financial-services-latest-news-list.rss",
        "rss",
        "PR Newswire Financial",
    ),
)


@lru_cache(maxsize=64)
def _cached_news_retriever(
    user_agent: str,
    feeds_key: FeedConfigKey,
    rate_limit_secs: float,
) -> NewsRetriever:
    """Build or reuse a retriever for one feed/user-agent configuration."""
    return NewsRetriever(
        list(feeds_key),
        user_agent,
        rate_limit_secs=rate_limit_secs,
    )


def create_news_retriever(
    user_agent: str,
    *,
    feeds: list[FeedTuple] | None = None,
    rate_limit_secs: float = 0.0,
) -> NewsRetriever:
    """Create or reuse a news retriever backed by the Rust extension."""
    configured_feeds = feeds if feeds is not None else list(_DEFAULT_RSS_FEEDS)
    return _cached_news_retriever(
        user_agent,
        _normalize_feeds(configured_feeds),
        float(rate_limit_secs),
    )
