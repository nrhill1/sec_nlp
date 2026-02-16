from .client import (
    NewsItem as NewsItem,
    NewsRetriever as NewsRetriever,
    NewswatchExtensionError as NewswatchExtensionError,
    create_news_retriever as create_news_retriever,
)

__all__ = [
    "NewswatchExtensionError",
    "NewsItem",
    "NewsRetriever",
    "create_news_retriever",
]
