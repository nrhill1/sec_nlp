"""Step functions for the news monitoring pipeline."""

from .correlate import correlate_news_items
from .fetch import fetch_news_items
from .match import match_news_items

__all__: tuple[str, ...] = (
    "correlate_news_items",
    "fetch_news_items",
    "match_news_items",
)
