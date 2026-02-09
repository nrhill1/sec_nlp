# src/sec_nlp/pipelines/presets/analyze/models.py
"""Data models for the analyze pipeline."""

from collections.abc import Mapping, Sequence
from typing import ClassVar, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from sec_nlp.core.types import coerce_json_value
from sec_nlp.pipelines import BasePipelineResult
from sec_nlp.pipelines.base.result import SummaryFieldValue
from sec_nlp.pipelines.serialization import round_score
from sec_nlp.pipelines.types import AnalysisResultDict
from sec_nlp.types import JsonDict, JsonValue

from .market import MarketEnrichment

type EvidenceSpan = dict[str, str | int | float]
type EntityValue = JsonValue
type StringListInput = list[str] | str | int | float | None

ANALYSIS_OUTPUT_SCHEMA_VERSION = "1.1"


def _normalize_key_point_item(item: StringListInput) -> str | None:
    if item is None:
        return None
    if isinstance(item, str):
        cleaned = item.strip()
        return cleaned if cleaned else None
    if isinstance(item, (int, float)):
        return str(item)
    if isinstance(item, Sequence) and not isinstance(item, str):
        parts: list[str] = []
        for part in item:
            if isinstance(part, str):
                cleaned = part.strip()
                if cleaned:
                    parts.append(cleaned)
            elif isinstance(part, (int, float)):
                parts.append(str(part))
        if parts:
            return " - ".join(parts)
    return None


class AnalysisInput(BaseModel):
    """Input schema for semantic analysis chain."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    chunk: str
    symbol: str
    matched_query: str | None = Field(
        default=None,
        description="Specific search query that matched this chunk",
    )
    matched_queries: list[str] | None = Field(
        default=None,
        description="List of matching queries (ordered by relevance)",
    )
    context: str | None = Field(
        default=None,
        description="Additional context for analysis (optional)",
    )
    topic_hits: list[str] | None = Field(
        default=None,
        description="Topic keywords that matched this chunk",
    )
    analysis_instructions: str | None = Field(
        default=None,
        description="Prompt instructions for which analysis fields to return",
    )


class AnalysisResult(BasePipelineResult):
    """Result model for individual chunk analysis."""

    pipeline_type: ClassVar[Literal["analyze"]] = "analyze"
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="ignore",
        defer_build=True,
        use_attribute_docstrings=False,
        str_strip_whitespace=True,
        frozen=True,
    )

    is_relevant: bool = Field(
        default=False,
        description="Whether the content is relevant to the analysis task",
    )
    confidence_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score for relevance (0.0-1.0)",
    )
    summary: str | None = Field(
        default=None,
        description="Summary of the analyzed content",
    )
    key_points: list[str] = Field(
        default_factory=list,
        description="Key points extracted from content",
    )
    reasoning: str | None = Field(
        default=None,
        description="Explanation of the analysis",
    )
    query_match_terms: list[str] = Field(
        default_factory=list,
        description="Exact query terms found in the chunk",
    )
    missing_query_terms: list[str] = Field(
        default_factory=list,
        description="High-signal query terms missing from the chunk",
    )
    binding_status: str | None = Field(
        default=None,
        description="Binding status for agreements or commitments",
    )
    contingencies: list[str] = Field(
        default_factory=list,
        description="Conditions or contingencies stated in the text",
    )
    impact_channels: list[str] = Field(
        default_factory=list,
        description="Financial impact channels inferred from the text",
    )
    impact_direction: str | None = Field(
        default=None,
        description="Direction of expected financial impact",
    )
    impact_magnitude: str | None = Field(
        default=None,
        description="Magnitude of expected financial impact",
    )
    impact_horizon: str | None = Field(
        default=None,
        description="Timing horizon for expected financial impact",
    )
    impact_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence in the impact assessment",
    )
    impact_rationale: str | None = Field(
        default=None,
        description="Justification for the impact assessment",
    )
    extracted_entities: dict[str, EntityValue] = Field(
        default_factory=dict,
        description="Named entities extracted from content",
    )
    compensation_data: JsonDict | None = Field(
        default=None,
        description="Compensation breakdown when available",
    )
    proposal_info: JsonDict | None = Field(
        default=None,
        description="Proxy proposal details when available",
    )
    performance_metrics: list[JsonValue] = Field(
        default_factory=list,
        description="Compensation performance metrics mentioned in the chunk",
    )
    peer_set: list[JsonValue] = Field(
        default_factory=list,
        description="Peer group companies referenced for compensation benchmarking",
    )
    pay_for_performance_flags: list[JsonValue] = Field(
        default_factory=list,
        description="Pay-for-performance alignment/misalignment indicators",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Classifier tags or labels assigned to the chunk",
    )
    evidence_spans: list[EvidenceSpan] = Field(
        default_factory=list,
        description="Quoted excerpts or span positions that support the analysis",
    )
    source_excerpt: str | None = Field(
        default=None,
        description="Short excerpt from the chunk to aid traceability",
    )
    severity: str | None = Field(
        default=None,
        description="Relative severity/materiality for the finding (e.g., low/medium/high)",
    )
    sentiment: str | None = Field(
        default=None,
        description="Sentiment or polarity of the chunk",
    )
    forward_looking: bool = Field(
        default=False,
        description="Whether the text contains forward-looking statements",
    )
    follow_up_questions: list[str] = Field(
        default_factory=list,
        description="Questions an analyst should pursue based on this chunk",
    )

    @field_validator("impact_confidence", mode="before")
    @classmethod
    def _coerce_impact_confidence(cls, v: JsonValue) -> float | None:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return round_score(v)
        if isinstance(v, str):
            cleaned = v.strip().lower()
            if not cleaned:
                return None
            if cleaned in {"low", "medium", "high"}:
                mapping = {"low": 0.3, "medium": 0.6, "high": 0.85}
                return round_score(mapping[cleaned])
            try:
                return round_score(float(cleaned))
            except ValueError:
                return None
        return None

    @field_validator("key_points", mode="before")
    @classmethod
    def _coerce_key_points(
        cls, v: StringListInput | list[StringListInput]
    ) -> list[str]:
        """Allow null/empty key_points from LLM output to be parsed."""
        if v is None:
            return []
        if isinstance(v, (int, float)):
            return [str(v)]
        if isinstance(v, str):
            cleaned = v.strip()
            return [cleaned] if cleaned else []
        if isinstance(v, Sequence) and not isinstance(v, str):
            items: list[str] = []
            for item in v:
                normalized = _normalize_key_point_item(item)
                if normalized:
                    items.append(normalized)
            return items
        return []

    @field_validator("evidence_spans", mode="before")
    @classmethod
    def _coerce_evidence_spans(cls, v: JsonValue) -> list[EvidenceSpan]:
        """Normalize evidence spans from LLM output."""
        if v is None:
            return []
        if isinstance(v, str):
            cleaned = v.strip()
            if not cleaned:
                return []
            return []
        if isinstance(v, Sequence) and not isinstance(v, str):
            spans: list[EvidenceSpan] = []
            for item in v:
                if isinstance(item, dict):
                    span: EvidenceSpan = {
                        str(k): val
                        for k, val in item.items()
                        if isinstance(val, (str, int, float))
                    }
                    if span:
                        spans.append(span)
            return spans
        if isinstance(v, dict):
            span: EvidenceSpan = {
                str(k): val
                for k, val in v.items()
                if isinstance(val, (str, int, float))
            }
            return [span] if span else []
        return []

    @field_validator(
        "tags",
        "follow_up_questions",
        "query_match_terms",
        "missing_query_terms",
        "impact_channels",
        "contingencies",
        "performance_metrics",
        "peer_set",
        "pay_for_performance_flags",
        mode="before",
    )
    @classmethod
    def _coerce_list_fields(cls, v: StringListInput) -> list[str]:
        """Normalize optional list fields from LLM output."""
        if v is None:
            return []
        if isinstance(v, (int, float)):
            return [str(v)]
        if isinstance(v, str):
            cleaned = v.strip()
            return [cleaned] if cleaned else []
        if isinstance(v, Sequence) and not isinstance(v, str):
            return [item for item in v if isinstance(item, str)]
        return []

    @model_validator(mode="before")
    @classmethod
    def _normalize_llm_payload(cls, data: JsonDict) -> JsonValue:
        """Normalize common LLM schema variants before validation."""
        if not isinstance(data, dict):
            return data

        normalized: dict[str, JsonValue] = {}
        for key, value in data.items():
            if isinstance(key, str):
                normalized_value = coerce_json_value(value)
                if normalized_value is not None:
                    normalized[key] = normalized_value

        if "is_relevant" not in normalized:
            if "is_relatively_relevant" in normalized:
                normalized["is_relevant"] = normalized.pop(
                    "is_relatively_relevant"
                )
            elif "relevant" in normalized:
                normalized["is_relevant"] = normalized.pop("relevant")

        entities = normalized.get("extracted_entities")
        if entities is None:
            return normalized

        if isinstance(entities, Sequence) and not isinstance(entities, str):
            normalized_entities: dict[str, JsonValue] = {}
            for idx, item in enumerate(entities):
                key = f"item_{idx}"
                if isinstance(item, dict):
                    name = item.get("name")
                    if isinstance(name, str) and name.strip():
                        key = name.strip()
                if key in normalized_entities:
                    key = f"{key}_{idx}"
                normalized_item = coerce_json_value(item)
                if normalized_item is not None:
                    normalized_entities[key] = normalized_item
            normalized["extracted_entities"] = normalized_entities
        elif not isinstance(entities, Mapping):
            normalized_entity = coerce_json_value(entities)
            if normalized_entity is not None:
                normalized["extracted_entities"] = {"value": normalized_entity}
            else:
                normalized["extracted_entities"] = {}

        return normalized

    def summary_fields(self) -> dict[str, SummaryFieldValue]:
        fields: dict[str, SummaryFieldValue] = {}
        fields.update(self.base_summary_fields())
        fields["confidence"] = self.confidence_score
        return fields


class FilingInfo(BaseModel):
    """Filing metadata for output."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        defer_build=True,
        str_strip_whitespace=True,
    )

    accession_number: str | None = None
    form_type: str | None = None
    acceptance_date: str | None = None
    filing_date: str | None = None


class ExecutiveSummary(BaseModel):
    """High-level summary for quick scanning."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        defer_build=True,
        str_strip_whitespace=True,
    )

    status: str = Field(
        description="One-line status: e.g., '5 relevant findings (avg confidence 0.82)'"
    )
    result_count: int = Field(
        default=0,
        description="Total number of ranked results included in the output",
    )
    total_chunks: int = 0
    relevant_count: int = 0
    average_confidence: float = 0.0
    top_tags: list[str] = Field(default_factory=list)
    top_topics: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(
        default_factory=list, description="Top 5 key points across all results"
    )


class ExecutiveCompSummary(BaseModel):
    """Executive compensation summary extracted from proxy filings."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        defer_build=True,
        str_strip_whitespace=True,
    )

    executives: list[JsonDict] = Field(
        default_factory=list,
        description="Executives and roles mentioned in the filing",
    )
    compensation_items: list[JsonDict] = Field(
        default_factory=list,
        description="Compensation breakdown entries from the filing",
    )
    performance_metrics: list[JsonValue] = Field(
        default_factory=list,
        description="Performance metrics tied to compensation outcomes",
    )
    peer_set: list[JsonValue] = Field(
        default_factory=list,
        description="Peer companies used for compensation benchmarking",
    )
    pay_for_performance_flags: list[JsonValue] = Field(
        default_factory=list,
        description="Pay-for-performance alignment/misalignment notes",
    )
    notes: list[JsonValue] = Field(
        default_factory=list,
        description="Additional executive compensation observations",
    )


class AnalysisDiagnostics(BaseModel):
    """Diagnostic information for debugging and performance analysis."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        defer_build=True,
        str_strip_whitespace=True,
    )

    chunks_analyzed: int = 0
    chunks_successful: int = 0
    chunks_failed: int = 0
    chunks_relevant: int = 0
    success_rate: float = 0.0
    relevant_rate: float = 0.0
    timings: dict[str, float] = Field(default_factory=dict)
    confidence_threshold: float = 0.5


class OutputProvenance(BaseModel):
    """Metadata describing how the analysis output was produced."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        defer_build=True,
        str_strip_whitespace=True,
    )

    run_id: UUID | None = None
    pipeline_version: str | None = None
    model_name: str | None = None
    confidence_mode: str | None = None
    prompt_path: str | None = None
    prompt_version: str | None = None
    schema_version: str = ANALYSIS_OUTPUT_SCHEMA_VERSION


class Aggregates(BaseModel):
    """Aggregated statistics from analysis results."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        defer_build=True,
        str_strip_whitespace=True,
    )

    tag_frequency: dict[str, int] = Field(default_factory=dict)
    sentiment_breakdown: dict[str, int] = Field(default_factory=dict)
    sections_covered: dict[str, int] = Field(default_factory=dict)
    topic_hits_frequency: dict[str, int] = Field(default_factory=dict)
    impact_channel_frequency: dict[str, int] = Field(default_factory=dict)
    impact_horizon_frequency: dict[str, int] = Field(default_factory=dict)
    impact_direction_frequency: dict[str, int] = Field(default_factory=dict)
    impact_magnitude_frequency: dict[str, int] = Field(default_factory=dict)
    binding_status_frequency: dict[str, int] = Field(default_factory=dict)
    forward_looking_count: int = 0


class AnalysisOutput(BaseModel):
    """Structured output for a single filing analysis."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        defer_build=True,
        str_strip_whitespace=True,
    )

    symbol: str
    search_queries: list[str] = Field(
        default_factory=list,
        description="Search queries used to retrieve analyzed chunks",
    )
    filing: FilingInfo
    executive_summary: ExecutiveSummary
    executive_comp_summary: ExecutiveCompSummary | None = Field(
        default=None,
        description="Executive compensation summary when available",
    )
    aggregates: Aggregates
    diagnostics: AnalysisDiagnostics
    provenance: OutputProvenance | None = None
    market_enrichment: MarketEnrichment | None = Field(
        default=None,
        description="Aggregated market quotes for the requested date range",
    )
    market_correlation: JsonDict | None = Field(
        default=None,
        description="Structured correlation summary between the filing and the market window",
    )
    results: list[AnalysisResultDict] = Field(
        default_factory=list, description="Relevant analysis results"
    )
    results_by_query: dict[str, list[AnalysisResultDict]] = Field(
        default_factory=dict,
        description="Results grouped by matched search query",
    )
    results_by_section: dict[str, list[AnalysisResultDict]] = Field(
        default_factory=dict,
        description="Results grouped by filing section number",
    )
    relationship_timeline: dict[str, list[JsonDict]] = Field(
        default_factory=dict,
        description="Related filings grouped by relationship type",
    )


class AnalyzeResult(BasePipelineResult):
    """Result model for overall semantic search pipeline."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        defer_build=True,
        str_strip_whitespace=True,
    )

    pipeline_type: ClassVar[Literal["analyze"]] = "analyze"

    def summary_fields(self) -> dict[str, SummaryFieldValue]:
        fields: dict[str, SummaryFieldValue] = {}
        fields.update(self.base_summary_fields())
        return fields
