"""Entity and event extraction helpers backed by the Rust `entity` extension."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from importlib import import_module
from types import ModuleType
from typing import Any, cast

from langchain_core.documents import Document
from pydantic import BaseModel, ConfigDict


class EntityExtensionError(RuntimeError):
    """Raised when the Rust `entity` extension is unavailable."""


class Entity(BaseModel):
    """Normalized entity mention."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    entity_type: str
    start: int
    end: int
    normalized: str = ""


class EventMention(BaseModel):
    """Normalized event mention."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: str
    text: str
    start: int
    end: int
    confidence: float


@lru_cache(maxsize=1)
def _load_entity_module() -> ModuleType:
    try:
        return import_module("entity")
    except Exception as exc:  # pragma: no cover - depends on extension install
        raise EntityExtensionError(
            "entity extension is not available; build it with "
            "`make rs-ent-dev` or `make build-ext`."
        ) from exc


@lru_cache(maxsize=1)
def _get_entity_tagger() -> Any:
    return _load_entity_module().EntityTagger()


def _field(raw: object, name: str) -> Any:
    if isinstance(raw, Mapping):
        return cast("Mapping[str, Any]", raw).get(name)
    return getattr(raw, name, None)


def _to_entity(raw_entity: object) -> Entity:
    normalized = _field(raw_entity, "normalized")
    return Entity(
        text=str(_field(raw_entity, "text") or ""),
        entity_type=str(_field(raw_entity, "entity_type") or ""),
        start=int(_field(raw_entity, "start") or 0),
        end=int(_field(raw_entity, "end") or 0),
        normalized="" if normalized is None else str(normalized),
    )


def _to_event(raw_event: object) -> EventMention:
    return EventMention(
        event_type=str(_field(raw_event, "event_type") or ""),
        text=str(_field(raw_event, "text") or ""),
        start=int(_field(raw_event, "start") or 0),
        end=int(_field(raw_event, "end") or 0),
        confidence=float(_field(raw_event, "confidence") or 0.0),
    )


def extract_entities(text: str) -> list[Entity]:
    """Extract entities from filing text."""
    if not text:
        return []
    raw_entities = _get_entity_tagger().tag_text(text)
    return [_to_entity(raw_entity) for raw_entity in raw_entities]


def detect_events(text: str) -> list[EventMention]:
    """Detect event phrases from filing text."""
    if not text:
        return []
    raw_events = _get_entity_tagger().detect_events(text)
    return [_to_event(raw_event) for raw_event in raw_events]


def enrich_documents(docs: list[Document]) -> list[Document]:
    """Attach entity and event metadata to documents."""
    enriched: list[Document] = []
    for doc in docs:
        metadata = dict(doc.metadata)
        metadata["entities"] = [
            entity.model_dump() for entity in extract_entities(doc.page_content)
        ]
        metadata["events"] = [
            event.model_dump() for event in detect_events(doc.page_content)
        ]
        enriched.append(doc.model_copy(update={"metadata": metadata}))
    return enriched


__all__ = (
    "EntityExtensionError",
    "Entity",
    "EventMention",
    "extract_entities",
    "detect_events",
    "enrich_documents",
)
