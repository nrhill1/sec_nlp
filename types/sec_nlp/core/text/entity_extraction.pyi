from __future__ import annotations

from types import ModuleType
from typing import Any

from langchain_core.documents import Document as Document
from pydantic import BaseModel

class EntityExtensionError(RuntimeError): ...

class Entity(BaseModel):
    text: str
    entity_type: str
    start: int
    end: int
    normalized: str

class EventMention(BaseModel):
    event_type: str
    text: str
    start: int
    end: int
    confidence: float

def _load_entity_module() -> ModuleType: ...
def _get_entity_tagger() -> Any: ...
def _field(raw: object, name: str) -> Any: ...
def _to_entity(raw_entity: object) -> Entity: ...
def _to_event(raw_event: object) -> EventMention: ...
def extract_entities(text: str) -> list[Entity]: ...
def detect_events(text: str) -> list[EventMention]: ...
def enrich_documents(docs: list[Document]) -> list[Document]: ...
