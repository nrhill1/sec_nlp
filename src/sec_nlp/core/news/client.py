# src/sec_nlp/core/news/client.py
"""Thin wrapper around the Rust `newswatch` extension."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from importlib import import_module
from types import ModuleType

from pydantic import BaseModel, ConfigDict, Field


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
    except Exception as exc:  # pragma: no cover - depends on extension install
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
    return [_to_news_item(raw_item) for raw_item in raw_items]


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
        self._module = module or _load_newswatch_module()
        self._client = self._module.NewsClient(
            feeds,
            user_agent,
            float(rate_limit_secs),
        )

    def fetch(
        self,
        keywords: list[str],
        max_results: int = 100,
    ) -> list[NewsItem]:
        raw_items = self._client.fetch(list(keywords), int(max_results))
        return _to_news_items(raw_items)


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


def create_news_retriever(
    user_agent: str,
    *,
    feeds: list[tuple[str, str, str]] | None = None,
    rate_limit_secs: float = 0.0,
) -> NewsRetriever:
    """Create a news retriever backed by the Rust extension."""
    configured_feeds = feeds if feeds is not None else list(_DEFAULT_RSS_FEEDS)
    return NewsRetriever(
        configured_feeds,
        user_agent,
        rate_limit_secs=rate_limit_secs,
    )
