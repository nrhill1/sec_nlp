from __future__ import annotations

from types import ModuleType
from typing import Any

from pydantic import BaseModel

class NewswatchExtensionError(RuntimeError): ...

class NewsItem(BaseModel):
    title: str
    url: str
    source: str
    published_at: str | None
    matched_keywords: list[str]
    snippet: str | None

def _load_newswatch_module() -> ModuleType: ...
def _field(raw_item: object, name: str) -> Any: ...
def _to_news_item(raw_item: object) -> NewsItem: ...
def _to_news_items(raw_items: list[object]) -> list[NewsItem]: ...

class NewsRetriever:
    def __init__(
        self,
        feeds: list[tuple[str, str, str]],
        user_agent: str,
        *,
        rate_limit_secs: float = ...,
        module: ModuleType | None = ...,
    ) -> None: ...
    def fetch(
        self,
        keywords: list[str],
        max_results: int = ...,
    ) -> list[NewsItem]: ...

def create_news_retriever(
    user_agent: str,
    *,
    feeds: list[tuple[str, str, str]] | None = ...,
    rate_limit_secs: float = ...,
) -> NewsRetriever: ...
