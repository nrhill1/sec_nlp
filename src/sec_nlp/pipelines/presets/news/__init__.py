# src/sec_nlp/pipelines/presets/news/__init__.py
"""News monitoring pipeline."""

from .config import NewsSettings
from .models import (
    FilingEvent,
    NewsCluster,
    NewsCorrelation,
    NewsHeadline,
    NewsResult,
    NewsTimelineEntry,
)
from .pipeline import NewsPipeline

__all__: tuple[str, ...] = (
    "FilingEvent",
    "NewsCluster",
    "NewsCorrelation",
    "NewsHeadline",
    "NewsPipeline",
    "NewsResult",
    "NewsSettings",
    "NewsTimelineEntry",
)
