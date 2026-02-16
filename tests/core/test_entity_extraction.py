"""Tests for the entity extraction wrapper module."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from sec_nlp.core.text import entity_extraction


def test_load_entity_module_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entity_extraction._load_entity_module.cache_clear()
    entity_extraction._get_entity_tagger.cache_clear()

    def fail_import(_name: str) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(entity_extraction, "import_module", fail_import)

    with pytest.raises(
        entity_extraction.EntityExtensionError,
        match="entity extension is not available",
    ):
        entity_extraction._load_entity_module()

    entity_extraction._load_entity_module.cache_clear()
    entity_extraction._get_entity_tagger.cache_clear()


def test_extract_entities_and_detect_events_map_native_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, str] = {}

    fake_tagger = SimpleNamespace(
        tag_text=lambda text: (
            calls.setdefault("tag_text", text),
            [
                {
                    "text": "Rule 10b-5",
                    "entity_type": "REGULATION",
                    "start": 0,
                    "end": 10,
                    "normalized": "Rule 10b-5",
                },
                SimpleNamespace(
                    text="Apple Inc.",
                    entity_type="ORG",
                    start=14,
                    end=24,
                    normalized=None,
                ),
            ],
        )[1],
        detect_events=lambda text: (
            calls.setdefault("detect_events", text),
            [
                SimpleNamespace(
                    event_type="merger",
                    text="business combination",
                    start=30,
                    end=50,
                    confidence=0.95,
                )
            ],
        )[1],
    )
    monkeypatch.setattr(
        entity_extraction, "_get_entity_tagger", lambda: fake_tagger
    )

    text = "Rule 10b-5 and Apple Inc. entered a business combination."
    entities = entity_extraction.extract_entities(text)
    events = entity_extraction.detect_events(text)

    assert calls["tag_text"] == text
    assert calls["detect_events"] == text
    assert [entity.entity_type for entity in entities] == ["REGULATION", "ORG"]
    assert entities[1].normalized == ""
    assert events[0].event_type == "merger"
    assert events[0].confidence == pytest.approx(0.95)


def test_enrich_documents_adds_entity_and_event_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        entity_extraction,
        "extract_entities",
        lambda _text: [
            entity_extraction.Entity(
                text="CUSIP 037833100",
                entity_type="CUSIP",
                start=0,
                end=14,
                normalized="037833100",
            )
        ],
    )
    monkeypatch.setattr(
        entity_extraction,
        "detect_events",
        lambda _text: [
            entity_extraction.EventMention(
                event_type="restatement",
                text="restatement",
                start=20,
                end=31,
                confidence=0.8,
            )
        ],
    )

    original = Document(
        page_content="CUSIP 037833100 with potential restatement language.",
        metadata={"section": "Item 1A"},
    )
    enriched_docs = entity_extraction.enrich_documents([original])

    assert "entities" not in original.metadata
    assert "events" not in original.metadata
    assert len(enriched_docs) == 1
    assert enriched_docs[0].metadata["section"] == "Item 1A"
    assert enriched_docs[0].metadata["entities"][0]["entity_type"] == "CUSIP"
    assert enriched_docs[0].metadata["events"][0]["event_type"] == "restatement"
