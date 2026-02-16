"""Manual stub for the `entity` native extension."""

from __future__ import annotations

class Entity:
    entity_type: str
    text: str
    start: int
    end: int
    normalized: str | None

class EventMention:
    event_type: str
    text: str
    start: int
    end: int
    confidence: float

class EntityTagger:
    def __init__(self, dictionary_path: str | None = ...) -> None: ...
    def tag_text(self, text: str) -> list[Entity]: ...
    def detect_events(self, text: str) -> list[EventMention]: ...
    def tag_and_detect(
        self, text: str
    ) -> tuple[list[Entity], list[EventMention]]: ...
