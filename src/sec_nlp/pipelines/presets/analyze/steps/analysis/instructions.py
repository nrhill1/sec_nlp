# src/sec_nlp/pipelines/presets/analyze/steps/analysis/instructions.py
"""Prompt instruction builder for analyze schema fields."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from sec_nlp.core.infra.logger import logger

ANALYSIS_FIELD_ORDER: list[str] = [
    "is_relevant",
    "confidence_score",
    "summary",
    "key_points",
    "reasoning",
    "query_match_terms",
    "missing_query_terms",
    "binding_status",
    "contingencies",
    "impact_channels",
    "impact_direction",
    "impact_magnitude",
    "impact_horizon",
    "impact_confidence",
    "impact_rationale",
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
    "query_match_terms": (
        "**query_match_terms** (list[string]): Exact query terms that appear in the text (case-insensitive match). Use [] if no query or none found."
    ),
    "missing_query_terms": (
        "**missing_query_terms** (list[string]): High-signal query terms that are absent from the text. Use [] if none or no query."
    ),
    "binding_status": (
        '**binding_status** (string | null): "binding", "non_binding", "conditional", "terminated", or "unknown" for agreements/commitments.'
    ),
    "contingencies": (
        "**contingencies** (list[string]): Explicit conditions/approvals/requirements tied to the event; [] if none."
    ),
    "impact_channels": (
        '**impact_channels** (list[string]): Financial impact vectors such as "revenue", "costs", "margin", "capex", "liquidity", "balance_sheet", "production", "pricing", "regulatory", "legal", "tax", "strategy". [] if none.'
    ),
    "impact_direction": (
        '**impact_direction** (string | null): "positive", "negative", "mixed", "neutral", or "unclear".'
    ),
    "impact_magnitude": (
        '**impact_magnitude** (string | null): "low", "medium", "high", "none", or "unclear".'
    ),
    "impact_horizon": (
        '**impact_horizon** (string | null): "near_term", "mid_term", "long_term", or "unclear".'
    ),
    "impact_confidence": (
        "**impact_confidence** (0.0-1.0 | null): Confidence in the impact assessment; null if no impact assessment."
    ),
    "impact_rationale": (
        "**impact_rationale** (string | null): 1-2 sentence justification linking the text to expected financial impact; null if unclear."
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

ANALYSIS_FIELD_DESCRIPTIONS_COMPACT: dict[str, str] = {
    "is_relevant": (
        "**is_relevant** (boolean): True only when the chunk materially addresses a query/topic."
    ),
    "confidence_score": (
        "**confidence_score** (0.0-1.0): Confidence in the relevance judgment."
    ),
    "summary": (
        "**summary** (string | null): 1-2 factual sentences tied to the query/topic; null if not relevant."
    ),
    "key_points": (
        "**key_points** (list[string]): Up to 3 concise evidence bullets; [] when not relevant."
    ),
    "reasoning": (
        "**reasoning** (string): Brief rationale tied to explicit evidence or non-relevance."
    ),
    "query_match_terms": (
        "**query_match_terms** (list[string]): Query terms present in text."
    ),
    "missing_query_terms": (
        "**missing_query_terms** (list[string]): Important query terms absent from text."
    ),
    "binding_status": (
        '**binding_status** (string | null): "binding", "non_binding", "conditional", "terminated", or "unknown".'
    ),
    "contingencies": (
        "**contingencies** (list[string]): Explicit conditions/approvals required."
    ),
    "impact_channels": (
        "**impact_channels** (list[string]): Main financial channels affected."
    ),
    "impact_direction": (
        '**impact_direction** (string | null): "positive", "negative", "mixed", "neutral", or "unclear".'
    ),
    "impact_magnitude": (
        '**impact_magnitude** (string | null): "low", "medium", "high", "none", or "unclear".'
    ),
    "impact_horizon": (
        '**impact_horizon** (string | null): "near_term", "mid_term", "long_term", or "unclear".'
    ),
    "impact_confidence": (
        "**impact_confidence** (0.0-1.0 | null): Confidence in impact assessment."
    ),
    "impact_rationale": (
        "**impact_rationale** (string | null): Short link between text and impact."
    ),
    "extracted_entities": (
        "**extracted_entities** (object): Entities grouped by type (companies, people, dates, amounts, locations)."
    ),
    "tags": ("**tags** (list[string]): Short topical labels."),
    "evidence_spans": (
        "**evidence_spans** (list[object]): Up to 2 short supporting snippets."
    ),
    "source_excerpt": (
        "**source_excerpt** (string | null): Best evidentiary quote (<=200 chars)."
    ),
    "severity": (
        '**severity** (string | null): "low", "medium", "high", or null.'
    ),
    "sentiment": (
        '**sentiment** (string | null): "negative", "neutral", "positive", or null.'
    ),
    "forward_looking": (
        "**forward_looking** (boolean): True when forward-looking language is present."
    ),
    "follow_up_questions": (
        "**follow_up_questions** (list[string]): Up to 3 next-step analyst questions."
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
    style: Literal["full", "compact"] = "full"
    """Instruction verbosity profile."""

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
        description_map = (
            ANALYSIS_FIELD_DESCRIPTIONS_COMPACT
            if self.style == "compact"
            else ANALYSIS_FIELD_DESCRIPTIONS
        )
        lines: list[str] = []
        for idx, field in enumerate(ordered, start=1):
            description = description_map.get(field, field)
            lines.append(f"{idx}. {description}")

        if not lines:
            return ""

        raw = "\n".join(lines)
        return raw.replace("\n", "\n  ")
