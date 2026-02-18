"""News retrieval helpers backed by native extensions."""

from .client import (
    NewsItem,
    NewsRetriever,
    NewswatchExtensionError,
    create_news_retriever,
)

__all__ = (
    "NewswatchExtensionError",
    "NewsItem",
    "NewsRetriever",
    "create_news_retriever",
)
