"""Event detection pipeline."""

from .config import EventsSettings
from .models import DetectedEvent, EventHeadline, EventImpact, EventsResult
from .pipeline import EventsPipeline

__all__: tuple[str, ...] = (
    "DetectedEvent",
    "EventHeadline",
    "EventImpact",
    "EventsPipeline",
    "EventsResult",
    "EventsSettings",
)
