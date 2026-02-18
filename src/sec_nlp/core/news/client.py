"""Thin wrapper around the Rust `newswatch` extension."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from importlib import import_module
from types import ModuleType
from typing import Any, cast

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
    try:
        return import_module("newswatch")
    except Exception as exc:  # pragma: no cover - depends on extension install
        raise NewswatchExtensionError(
            "newswatch extension is not available; build it with "
            "`make rs-nw-dev` or `make build-ext`."
        ) from exc


def _field(raw_item: object, name: str) -> Any:
    if isinstance(raw_item, Mapping):
        return cast("Mapping[str, Any]", raw_item).get(name)
    return getattr(raw_item, name, None)


def _to_news_item(raw_item: object) -> NewsItem:
    return NewsItem(
        title=str(_field(raw_item, "title") or ""),
        url=str(_field(raw_item, "url") or ""),
        source=str(_field(raw_item, "source") or ""),
        published_at=_field(raw_item, "published_at"),
        matched_keywords=list(_field(raw_item, "matched_keywords") or []),
        snippet=_field(raw_item, "snippet"),
    )


def _to_news_items(raw_items: list[object]) -> list[NewsItem]:
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
