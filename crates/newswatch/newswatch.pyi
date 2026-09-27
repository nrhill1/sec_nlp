# crates/newswatch/newswatch.pyi
"""Manual stub for the `newswatch` native extension."""

from collections.abc import Awaitable

class NewsItem:
    title: str
    url: str
    source: str
    published_at: str | None
    matched_keywords: list[str]
    snippet: str | None

class NewsClient:
    def __init__(
        self,
        feeds: list[tuple[str, str, str]],
        user_agent: str,
        rate_limit_secs: float = ...,
    ) -> None: ...
    def fetch(
        self, keywords: list[str], max_results: int = ...
    ) -> list[NewsItem]: ...
    def fetch_async(
        self, keywords: list[str], max_results: int = ...
    ) -> Awaitable[list[NewsItem]]: ...
    def wait_idle_async(self) -> Awaitable[None]:
        """Acknowledge completion or cancellation of active native requests."""
