# src/sec_nlp/pipelines/presets/analyze/instructions.py
"""Prompt instruction builder for analyze schema fields."""

from __future__ import annotations

from pydantic import BaseModel

from sec_nlp.core.infra.logger import logger

ANALYSIS_FIELD_ORDER: list[str] = [
    "is_relevant",
    "confidence_score",
    "summary",
    "key_points",
    "reasoning",
    "extracted_entities",
    "tags",
    "evidence_spans",
    "source_excerpt",
    "severity",
    "sentiment",
    "forward_looking",
    "follow_up_questions",
]

ANALYSIS_FIELD_DESCRIPTIONS: dict[str, str] = {
    "is_relevant": (
        "**is_relevant** (boolean): True only if the content directly addresses at least one search query (when provided) or a configured topic; false for boilerplate/TOC/administrative content."
    ),
    "confidence_score": (
        "**confidence_score** (0.0-1.0): Confidence in the relevance assessment.\n"
        "   - 0.9-1.0: Directly answers a query with concrete evidence\n"
        "   - 0.7-0.9: Relevant to a query; useful details\n"
        "   - 0.5-0.7: Some topical overlap but limited substance\n"
        "   - Below 0.5: Low relevance; generic or administrative"
    ),
    "summary": (
        "**summary** (string | null): 2-3 sentence, fact-rich summary explicitly tied to the matched query/topic; only include details that directly support that intent; include entities, dates, amounts, and obligations when present; null if not relevant."
    ),
    "key_points": (
        "**key_points** (list[string]): 3-5 concise, fact-heavy bullets explicitly tied to the matched query/topic; include numbers/counterparties when available; [] if not relevant."
    ),
    "reasoning": (
        "**reasoning** (string): Brief rationale explicitly referencing the matched query/topic and the specific supporting detail(s) or why it is not relevant."
    ),
    "extracted_entities": (
        "**extracted_entities** (object): Named entities by type: companies, people, dates, amounts, locations (each a list; [] if none)."
    ),
    "tags": (
        '**tags** (list[string]): Short labels like "risk", "accounting", "governance", "legal", "liquidity", "strategy", "operations"; [] if none.'
    ),
    "evidence_spans": (
        '**evidence_spans** (list[object]): Up to 2 supporting snippets. Each: {"text": "<short quote>", "start_char": <int|optional>, "end_char": <int|optional>}. Use [] if none.'
    ),
    "source_excerpt": (
        "**source_excerpt** (string | null): A single short quote (<=200 chars) that best evidences the finding; null if not relevant."
    ),
    "severity": (
        '**severity** (string | null): One of "low", "medium", "high" if applicable; otherwise null.'
    ),
    "sentiment": (
        '**sentiment** (string | null): "negative", "neutral", or "positive" when discernible; null if unclear.'
    ),
    "forward_looking": (
        "**forward_looking** (boolean): True if the text contains forward-looking statements; else false."
    ),
    "follow_up_questions": (
        "**follow_up_questions** (list[string]): Up to 3 concise questions an analyst should pursue; [] if none."
    ),
}

REQUIRED_ANALYSIS_FIELDS: tuple[str, str] = (
    "is_relevant",
    "confidence_score",
)


class AnalysisInstructionBuilder(BaseModel):
    """Build prompt instructions for configured analysis fields."""

    analysis_fields: list[str] = []
    """List of analysis fields to include in instructions."""

    def build(self) -> str:
        """Return formatted instruction text for the prompt."""
        requested = [
            field.strip()
            for field in self.analysis_fields
            if isinstance(field, str) and field.strip()
        ]
        if not requested:
            requested = list(ANALYSIS_FIELD_ORDER)

        alias_map = {field.lower(): field for field in ANALYSIS_FIELD_ORDER}
        selected: set[str] = set()
        unknown: list[str] = []

        for field in requested:
            canonical = alias_map.get(field.lower())
            if canonical is None:
                unknown.append(field)
                continue
            selected.add(canonical)

        if unknown:
            logger.warning(
                "Ignoring unknown analysis_fields entries: %s",
                ", ".join(sorted(set(unknown))),
            )

        for required in REQUIRED_ANALYSIS_FIELDS:
            if required not in selected:
                selected.add(required)
                logger.warning(
                    "analysis_fields missing required field '%s'; adding it for pipeline consistency",
                    required,
                )

        ordered = [field for field in ANALYSIS_FIELD_ORDER if field in selected]
        lines: list[str] = []
        for idx, field in enumerate(ordered, start=1):
            description = ANALYSIS_FIELD_DESCRIPTIONS.get(field, field)
            lines.append(f"{idx}. {description}")

        if not lines:
            return ""

        raw = "\n".join(lines)
        return raw.replace("\n", "\n  ")
