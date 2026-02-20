"""Supply chain mapping runnable for exhibit and risk-factor text."""

from __future__ import annotations

import re
from collections.abc import Callable

from langchain_core.documents import Document
from langchain_core.runnables import RunnableConfig, RunnableSerializable
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.text.entity_extraction import (
    EntityExtensionError,
    extract_entities,
)
from sec_nlp.types import JsonValue

DocumentProvider = Callable[[str], list[Document]]
EntityExtractor = Callable[[str], list[str]]

_ENTITY_PATTERN = re.compile(
    r"\b[A-Z][A-Za-z0-9&.,'\-]*(?:\s+[A-Z][A-Za-z0-9&.,'\-]*){0,4}\b"
)
_STOPWORDS = {
    "The",
    "This",
    "That",
    "And",
    "For",
    "With",
    "Company",
    "Corporation",
    "Inc",
    "LLC",
}

_RELATIONSHIP_KEYWORDS: dict[str, tuple[str, ...]] = {
    "subsidiary": (
        "subsidiary",
        "subsidiaries",
        "wholly owned",
        "majority-owned",
    ),
    "supplier": ("supplier", "suppliers", "vendor", "vendors", "sourced"),
    "customer": ("customer", "customers", "client", "clients", "buyer"),
    "partner": (
        "partner",
        "partners",
        "alliance",
        "joint venture",
        "collaboration",
    ),
}


class SupplyChainMapInput(BaseModel):
    """Runnable input for supply-chain relationship extraction."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    symbol: str
    include_exhibits: bool = True
    include_risk_factors: bool = True


class RelatedEntity(BaseModel):
    """Structured relationship mention for a related entity."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    name: str
    relationship: str
    source_filing: str
    source_section: str
    confidence: float


class SupplyChainMapOutput(BaseModel):
    """Runnable output for first-degree supply-chain entities."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    symbol: str
    entities: list[RelatedEntity] = Field(default_factory=list)
    entity_count: int = 0


class SupplyChainMapRunnable(
    RunnableSerializable[SupplyChainMapInput, SupplyChainMapOutput]
):
    """Build first-degree supplier/customer/subsidiary/partner map."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    exhibit_provider: DocumentProvider | None = None
    risk_factor_provider: DocumentProvider | None = None
    entity_extractor: EntityExtractor | None = None

    def invoke(
        self,
        input: SupplyChainMapInput,
        config: RunnableConfig | None = None,
        **kwargs: JsonValue,
    ) -> SupplyChainMapOutput:
        _ = config
        _ = kwargs

        symbol = input.symbol.strip().upper()
        if not symbol:
            raise ValueError("symbol must be non-empty")

        docs_with_defaults: list[tuple[Document, str]] = []
        if input.include_exhibits and self.exhibit_provider is not None:
            docs_with_defaults.extend(
                (document, "Exhibit 21")
                for document in self.exhibit_provider(symbol)
            )
        if input.include_risk_factors and self.risk_factor_provider is not None:
            docs_with_defaults.extend(
                (document, "Item 1A")
                for document in self.risk_factor_provider(symbol)
            )

        deduped_entities: dict[tuple[str, str, str, str], RelatedEntity] = {}
        for document, default_section in docs_with_defaults:
            for entity in self._extract_related_entities(
                document=document,
                default_section=default_section,
            ):
                dedupe_key = (
                    entity.name.lower(),
                    entity.relationship,
                    entity.source_filing,
                    entity.source_section,
                )
                existing = deduped_entities.get(dedupe_key)
                if existing is None or entity.confidence > existing.confidence:
                    deduped_entities[dedupe_key] = entity

        entities = sorted(
            deduped_entities.values(),
            key=lambda entity: (
                entity.source_filing,
                entity.source_section,
                entity.relationship,
                entity.name,
            ),
        )

        return SupplyChainMapOutput(
            symbol=symbol,
            entities=entities,
            entity_count=len(entities),
        )

    def _extract_related_entities(
        self,
        *,
        document: Document,
        default_section: str,
    ) -> list[RelatedEntity]:
        text = document.page_content
        if not text.strip():
            return []

        metadata = (
            document.metadata if isinstance(document.metadata, dict) else {}
        )
        source_filing = (
            self._coerce_metadata_text(metadata.get("accession_number"))
            or self._coerce_metadata_text(metadata.get("accession"))
            or "unknown"
        )
        source_section = (
            self._coerce_metadata_text(metadata.get("section"))
            or self._coerce_metadata_text(metadata.get("source_section"))
            or default_section
        )

        extracted_entities = self._extract_entity_names(text)
        related_entities: list[RelatedEntity] = []
        for entity_name in extracted_entities:
            relationship = self._classify_relationship(
                text=text,
                entity_name=entity_name,
                default_section=source_section,
            )
            confidence = self._confidence_for_relationship(
                relationship=relationship,
                source_section=source_section,
            )
            related_entities.append(
                RelatedEntity(
                    name=entity_name,
                    relationship=relationship,
                    source_filing=source_filing,
                    source_section=source_section,
                    confidence=confidence,
                )
            )
        return related_entities

    def _extract_entity_names(self, text: str) -> list[str]:
        if self.entity_extractor is not None:
            names: set[str] = set()
            for name in self.entity_extractor(text):
                normalized = self._normalize_entity_name(name)
                if normalized is not None:
                    names.add(normalized)
            return sorted(names)

        extension_names = self._extract_org_names_from_extension(text)
        if extension_names is not None:
            return extension_names

        names: set[str] = set()
        for match in _ENTITY_PATTERN.finditer(text):
            normalized = self._normalize_entity_name(match.group(0))
            if normalized is not None:
                names.add(normalized)
        return sorted(names)

    @classmethod
    def _extract_org_names_from_extension(cls, text: str) -> list[str] | None:
        try:
            tagged_entities = extract_entities(text)
        except EntityExtensionError:
            return None

        names: set[str] = set()
        for tagged_entity in tagged_entities:
            if tagged_entity.entity_type.upper() != "ORG":
                continue
            normalized = cls._normalize_entity_name(
                tagged_entity.normalized or tagged_entity.text
            )
            if normalized is not None:
                names.add(normalized)
        return sorted(names)

    @staticmethod
    def _normalize_entity_name(name: str | None) -> str | None:
        if name is None:
            return None
        cleaned = " ".join(name.strip().split())
        if not cleaned:
            return None
        if cleaned in _STOPWORDS:
            return None
        if len(cleaned) < 3:
            return None
        return cleaned

    @staticmethod
    def _coerce_metadata_text(value: JsonValue) -> str | None:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return None

    @staticmethod
    def _classify_relationship(
        *,
        text: str,
        entity_name: str,
        default_section: str,
    ) -> str:
        lowered_text = text.lower()
        lowered_entity = entity_name.lower()
        occurrences: list[tuple[int, int]] = []
        start = lowered_text.find(lowered_entity)
        while start != -1:
            occurrences.append((start, start + len(lowered_entity)))
            start = lowered_text.find(lowered_entity, start + 1)

        trailing_distance_by_relationship: dict[str, int | None] = (
            dict.fromkeys(_RELATIONSHIP_KEYWORDS, None)
        )
        for _start_index, end_index in occurrences:
            trailing_window = lowered_text[end_index : end_index + 80]
            for relationship, keywords in _RELATIONSHIP_KEYWORDS.items():
                for keyword in keywords:
                    keyword_start = trailing_window.find(keyword)
                    if keyword_start == -1:
                        continue
                    existing_distance = trailing_distance_by_relationship[
                        relationship
                    ]
                    if (
                        existing_distance is None
                        or keyword_start < existing_distance
                    ):
                        trailing_distance_by_relationship[relationship] = (
                            keyword_start
                        )

        best_distance_by_relationship: dict[str, int | None] = dict.fromkeys(
            _RELATIONSHIP_KEYWORDS, None
        )
        for start_index, end_index in occurrences:
            left = max(0, start_index - 160)
            right = min(len(lowered_text), end_index + 120)
            window = lowered_text[left:right]
            anchor_index = start_index - left
            for relationship, keywords in _RELATIONSHIP_KEYWORDS.items():
                for keyword in keywords:
                    keyword_start = window.find(keyword)
                    while keyword_start != -1:
                        distance = abs(keyword_start - anchor_index)
                        existing_distance = best_distance_by_relationship[
                            relationship
                        ]
                        if (
                            existing_distance is None
                            or distance < existing_distance
                        ):
                            best_distance_by_relationship[relationship] = (
                                distance
                            )
                        keyword_start = window.find(keyword, keyword_start + 1)

        priority = {
            "subsidiary": 3,
            "supplier": 2,
            "customer": 1,
            "partner": 0,
        }
        trailing_relationships = [
            (distance, -priority[relationship], relationship)
            for relationship, distance in trailing_distance_by_relationship.items()
            if distance is not None
        ]
        if trailing_relationships:
            trailing_relationships.sort()
            return trailing_relationships[0][2]

        ranked_relationships = [
            (distance, -priority[relationship], relationship)
            for relationship, distance in best_distance_by_relationship.items()
            if distance is not None
        ]
        if ranked_relationships:
            ranked_relationships.sort()
            return ranked_relationships[0][2]

        if "exhibit" in default_section.lower():
            return "subsidiary"
        return "partner"

    @staticmethod
    def _confidence_for_relationship(
        *,
        relationship: str,
        source_section: str,
    ) -> float:
        base_confidence = {
            "subsidiary": 0.9,
            "supplier": 0.8,
            "customer": 0.8,
            "partner": 0.7,
        }.get(relationship, 0.6)
        if relationship == "subsidiary" and "exhibit" in source_section.lower():
            return 0.95
        return base_confidence
