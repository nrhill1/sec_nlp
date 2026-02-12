# module: `sec_nlp/core/text/entity_extraction.py` — Entity Extraction Wrapper

## Purpose

Thin Python wrapper around `crates/entity` integrating with the existing text processing layer. Provides `extract_entities()`, `detect_events()`, and `enrich_documents()` as the Python-facing API for the Rust entity/event tagger.

## Existing Implementations — Build vs. Reuse

**`spaCy`** (PyPI) is the standard Python NLP library with pretrained NER models. Supports custom entity types via training. However, its entity taxonomy (PERSON, ORG, GPE, etc.) does not include SEC-specific types (REGULATION, CUSIP, fiscal dates), and adding them requires training data and model retraining.

**`flair`** (PyPI) provides sequence labeling NER with good accuracy. Similar taxonomy limitations as spaCy — no SEC domain types out of the box.

**`gliner`** (PyPI) is a zero-shot NER model that accepts arbitrary entity type descriptions. Could extract custom types without training, but requires a ~500MB model and is slow for batch processing.

**Recommendation: Wrap `crates/entity` (custom Rust implementation).** The Rust crate provides the SEC-domain-specific entity types and event phrases that no existing Python NER library covers. This module is purely a wrapper + Pydantic model layer. If general-purpose NER is later needed (e.g., extracting person names from narrative text where regex fails), spaCy or gliner can be added as an optional enrichment step alongside the Rust tagger.

## File Structure

```
src/sec_nlp/core/text/entity_extraction.py   # Single file module
```

## Key APIs

```python
from sec_nlp.core.text.entity_extraction import (
    extract_entities,
    detect_events,
    enrich_documents,
    Entity,
    EventMention,
)

class Entity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    text: str
    entity_type: str       # ORG, PERSON, MONEY, DATE, REGULATION, CUSIP, ISIN
    start: int             # Character offset start
    end: int               # Character offset end
    normalized: str = ""   # Normalized value (e.g., "$1.2B" → "1200000000")

class EventMention(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: str        # merger, bankruptcy, restatement, delisting, etc.
    text: str              # Matched phrase
    start: int
    end: int
    confidence: float

def extract_entities(text: str) -> list[Entity]:
    """Call crates/entity EntityTagger.tag_text(), map to Pydantic models."""
    ...

def detect_events(text: str) -> list[EventMention]:
    """Call crates/entity EntityTagger.detect_events(), map to Pydantic models."""
    ...

def enrich_documents(docs: list[Document]) -> list[Document]:
    """Add 'entities' and 'events' metadata to each document."""
    ...
```

## Implementation Details

- Lazy-import `entity` module following `_load_market_module()` pattern from `sec_nlp/core/market.py`.
- Create a module-level `_tagger` singleton (initialized on first call) to avoid re-compiling regex/Aho-Corasick patterns.
- `enrich_documents()` iterates over documents, calls both `extract_entities()` and `detect_events()` on each document's text, and attaches results to metadata.
- The `Document` type used in `enrich_documents` should match the existing document type used in the analyze pipeline.

## Implementation Steps

1. Implement `Entity` and `EventMention` Pydantic models (frozen, extra="forbid").
2. Implement lazy-loading wrapper for the `entity` Rust module.
3. Implement `extract_entities()` — call `EntityTagger.tag_text()`, convert to `Entity` list.
4. Implement `detect_events()` — call `EntityTagger.detect_events()`, convert to `EventMention` list.
5. Implement `enrich_documents()` — batch enrichment of document metadata.
6. Add type stubs for `crates/entity` in `types/entity/__init__.pyi`.
7. Write tests: mock the `entity` module, verify model mapping and document enrichment. No network.

## Dependencies

- `crates/entity` (via lazy import)
- No new PyPI dependencies
