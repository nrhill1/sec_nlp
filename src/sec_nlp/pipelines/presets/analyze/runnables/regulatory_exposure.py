# src/sec_nlp/pipelines/presets/analyze/runnables/regulatory_exposure.py
"""Regulatory exposure runnable for filing-document regulatory mentions."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Callable

from langchain_core.documents import Document
from langchain_core.runnables import RunnableConfig, RunnableSerializable
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.text.entity_extraction import (
    EntityExtensionError,
    extract_entities,
)
from sec_nlp.types import JsonValue

RegulationExtractor = Callable[[str], list[str]]

_REGULATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Rule 10b-5", re.compile(r"\bRule\s+10b-5\b", re.IGNORECASE)),
    (
        "Section 13(a)",
        re.compile(r"\bSection\s+13(?:\s*\(a\))?\b", re.IGNORECASE),
    ),
    ("Section 16", re.compile(r"\bSection\s+16\b", re.IGNORECASE)),
    ("Dodd-Frank", re.compile(r"\bDodd[-\s]Frank\b", re.IGNORECASE)),
    (
        "Sarbanes-Oxley",
        re.compile(r"\bSarbanes[-\s]Oxley\b|\bSOX\b", re.IGNORECASE),
    ),
    (
        "Foreign Corrupt Practices Act",
        re.compile(
            r"\bFCPA\b|\bForeign Corrupt Practices Act\b",
            re.IGNORECASE,
        ),
    ),
    ("Clean Air Act", re.compile(r"\bClean Air Act\b", re.IGNORECASE)),
    ("Clean Water Act", re.compile(r"\bClean Water Act\b", re.IGNORECASE)),
    (
        "GDPR",
        re.compile(
            r"\bGDPR\b|\bGeneral Data Protection Regulation\b",
            re.IGNORECASE,
        ),
    ),
    ("HIPAA", re.compile(r"\bHIPAA\b", re.IGNORECASE)),
    (
        "CFPB",
        re.compile(
            r"\bCFPB\b|\bConsumer Financial Protection Bureau\b",
            re.IGNORECASE,
        ),
    ),
    (
        "FTC Act",
        re.compile(
            r"\bFTC Act\b|\bFederal Trade Commission Act\b",
            re.IGNORECASE,
        ),
    ),
)

_REGULATORY_BODY_BY_REGULATION: dict[str, str] = {
    "Rule 10b-5": "SEC",
    "Section 13(a)": "SEC",
    "Section 16": "SEC",
    "Dodd-Frank": "SEC",
    "Sarbanes-Oxley": "SEC",
    "Foreign Corrupt Practices Act": "DOJ/SEC",
    "Clean Air Act": "EPA",
    "Clean Water Act": "EPA",
    "GDPR": "EU",
    "HIPAA": "HHS",
    "CFPB": "CFPB",
    "FTC Act": "FTC",
}


class RegulatoryExposureInput(BaseModel):
    """Runnable input for regulatory exposure analysis."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    documents: list[Document] = Field(default_factory=list)
    compare_with: list[Document] = Field(default_factory=list)


class RegulatoryReference(BaseModel):
    """Aggregated mentions for a regulation and inferred regulator."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    regulation: str
    regulatory_body: str
    mention_count: int
    sections: list[str] = Field(default_factory=list)


class RegulatoryExposureOutput(BaseModel):
    """Runnable output for current filing regulatory exposure."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    references: list[RegulatoryReference] = Field(default_factory=list)
    total_mentions: int = 0
    top_regulators: list[str] = Field(default_factory=list)
    trend: dict[str, int] | None = None


class RegulatoryExposureRunnable(
    RunnableSerializable[RegulatoryExposureInput, RegulatoryExposureOutput]
):
    """Scan filing documents for regulatory references and trend deltas."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    regulation_extractor: RegulationExtractor | None = None

    def invoke(
        self,
        input: RegulatoryExposureInput,
        config: RunnableConfig | None = None,
        **kwargs: JsonValue,
    ) -> RegulatoryExposureOutput:
        _ = config
        _ = kwargs

        current_counts, current_sections = self._collect_counts(input.documents)
        references = self._build_references(current_counts, current_sections)
        total_mentions = sum(
            reference.mention_count for reference in references
        )
        top_regulators = self._top_regulators(references)

        trend: dict[str, int] | None = None
        if input.compare_with:
            previous_counts, _ = self._collect_counts(input.compare_with)
            trend = self._build_trend(current_counts, previous_counts)

        return RegulatoryExposureOutput(
            references=references,
            total_mentions=total_mentions,
            top_regulators=top_regulators,
            trend=trend,
        )

    def _collect_counts(
        self,
        documents: list[Document],
    ) -> tuple[dict[str, int], dict[str, set[str]]]:
        """Collect per-regulator counts from extracted regulation mentions."""
        counts: defaultdict[str, int] = defaultdict(int)
        sections_by_regulation: defaultdict[str, set[str]] = defaultdict(set)

        for document in documents:
            section = self._document_section(document)
            for regulation in self._extract_regulations(document.page_content):
                counts[regulation] += 1
                sections_by_regulation[regulation].add(section)

        return dict(counts), dict(sections_by_regulation)

    def _extract_regulations(self, text: str) -> list[str]:
        """Extract regulation mentions from model text and metadata."""
        if self.regulation_extractor is not None:
            extracted: list[str] = []
            for regulation in self.regulation_extractor(text):
                normalized = self._normalize_regulation(regulation)
                if normalized is not None:
                    extracted.append(normalized)
            return extracted

        extension_extracted = (
            self._extract_regulations_from_extension(text) or []
        )
        pattern_extracted = self._extract_regulations_from_patterns(text)

        if not extension_extracted:
            return pattern_extracted
        if not pattern_extracted:
            return extension_extracted

        extension_counts = Counter(extension_extracted)
        pattern_counts = Counter(pattern_extracted)
        merged: list[str] = []
        for regulation in sorted(set(extension_counts) | set(pattern_counts)):
            merged.extend(
                [regulation]
                * max(
                    extension_counts.get(regulation, 0),
                    pattern_counts.get(regulation, 0),
                )
            )
        return merged

    @staticmethod
    def _extract_regulations_from_patterns(text: str) -> list[str]:
        """Extract regulation references using regex pattern matches."""
        extracted: list[str] = []
        for regulation, pattern in _REGULATION_PATTERNS:
            for _ in pattern.finditer(text):
                extracted.append(regulation)
        return extracted

    @classmethod
    def _extract_regulations_from_extension(cls, text: str) -> list[str] | None:
        """Extract regulation references from extension-provided metadata."""
        try:
            tagged_entities = extract_entities(text)
        except EntityExtensionError:
            return None

        extracted: list[str] = []
        for tagged_entity in tagged_entities:
            if tagged_entity.entity_type.upper() != "REGULATION":
                continue
            normalized = cls._normalize_regulation(
                tagged_entity.normalized or tagged_entity.text
            )
            if normalized is not None:
                extracted.append(normalized)
        return extracted

    @staticmethod
    def _normalize_regulation(regulation: str) -> str | None:
        """Normalize regulation strings for stable deduplication and grouping."""
        cleaned = " ".join(regulation.strip().split())
        if not cleaned:
            return None
        for canonical, pattern in _REGULATION_PATTERNS:
            if pattern.search(cleaned):
                return canonical
        return cleaned

    @staticmethod
    def _document_section(document: Document) -> str:
        """Resolve the source section label for a matched document."""
        metadata = (
            document.metadata if isinstance(document.metadata, dict) else {}
        )
        section = metadata.get("section")
        if isinstance(section, str):
            normalized = section.strip()
            if normalized:
                return normalized
        return "Unknown"

    def _build_references(
        self,
        counts: dict[str, int],
        sections_by_regulation: dict[str, set[str]],
    ) -> list[RegulatoryReference]:
        """Build citation references for regulatory exposure output."""
        references: list[RegulatoryReference] = []
        for regulation, mention_count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        ):
            references.append(
                RegulatoryReference(
                    regulation=regulation,
                    regulatory_body=self._regulatory_body(regulation),
                    mention_count=mention_count,
                    sections=sorted(
                        sections_by_regulation.get(regulation, set())
                    ),
                )
            )
        return references

    @staticmethod
    def _regulatory_body(regulation: str) -> str:
        """Resolve the regulator body name for a regulation identifier."""
        return _REGULATORY_BODY_BY_REGULATION.get(regulation, "Unknown")

    @staticmethod
    def _top_regulators(references: list[RegulatoryReference]) -> list[str]:
        """Select top regulators by mention frequency and confidence."""
        body_counts: defaultdict[str, int] = defaultdict(int)
        for reference in references:
            body_counts[reference.regulatory_body] += reference.mention_count
        return [
            body
            for body, _ in sorted(
                body_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]

    @staticmethod
    def _build_trend(
        current_counts: dict[str, int],
        previous_counts: dict[str, int],
    ) -> dict[str, int] | None:
        """Build trend statistics for regulatory exposure across filings."""
        trend = {
            regulation: current_counts.get(regulation, 0)
            - previous_counts.get(regulation, 0)
            for regulation in sorted(set(current_counts) | set(previous_counts))
        }
        non_zero_trend = {
            regulation: delta
            for regulation, delta in trend.items()
            if delta != 0
        }
        return non_zero_trend or None
