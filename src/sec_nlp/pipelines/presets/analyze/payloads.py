# src/sec_nlp/pipelines/presets/analyze/payloads.py
"""Payload models for analyze search exports."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.types import JsonDict, JsonValue


class SearchStatsPayload(BaseModel):
    """Summary statistics for search results."""

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    average_score: float | None = None
    best_score: float | None = None
    symbols: JsonDict = Field(default_factory=dict)
    sections: JsonDict = Field(default_factory=dict)
    tag_frequency: JsonDict = Field(default_factory=dict)
    sentiment_breakdown: JsonDict = Field(default_factory=dict)


class SearchHighlightsPayload(BaseModel):
    """Highlight data for search exports."""

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    top_summaries: list[str] = Field(default_factory=list)


class SearchAnalysisResultPayload(BaseModel):
    """Optional fields for analyzed search hits."""

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    is_relevant: bool | None = None
    confidence_score: float | None = None
    summary: JsonValue | None = None
    key_points: list[JsonValue] | None = None
    reasoning: JsonValue | None = None
    tags: list[JsonValue] | None = None
    sentiment: JsonValue | None = None
    severity: JsonValue | None = None
    forward_looking: bool | None = None
    evidence_spans: list[JsonDict] | None = None
    source_excerpt: JsonValue | None = None
    extracted_entities: JsonDict | None = None
    follow_up_questions: list[JsonValue] | None = None
    source_metadata: JsonDict | None = None
    raw_chunk: JsonValue | None = None
    error: JsonValue | None = None
    exception: JsonValue | None = None
    chunk_preview: JsonValue | None = None


class SearchAnalysisPayload(BaseModel):
    """Analysis payload for search results."""

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    enabled: bool
    analyzed_hits: int
    results: list[SearchAnalysisResultPayload] = Field(default_factory=list)


class SearchResultPayload(BaseModel):
    """Payload for an individual search hit."""

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    score: float
    content: JsonValue
    metadata: JsonDict = Field(default_factory=dict)
    summary: JsonValue | None = None
    tags: JsonValue | None = None
    sentiment: JsonValue | None = None
    forward_looking: bool | None = None
    confidence_score: float | None = None


class SearchMatchPayload(BaseModel):
    """Matched query metadata for a unique search hit."""

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    query: JsonValue
    score: float


class SearchQuerySectionPayload(BaseModel):
    """Per-query section within a consolidated search export."""

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    query: JsonValue
    results_count: int
    stats: SearchStatsPayload
    highlights: SearchHighlightsPayload
    results: list[SearchResultPayload] = Field(default_factory=list)


class SearchUniqueResultPayload(BaseModel):
    """Unique search hit aggregated across queries."""

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    content: JsonValue
    metadata: JsonDict = Field(default_factory=dict)
    matched_queries: list[SearchMatchPayload] = Field(default_factory=list)
    best_score: float | None = None


class SearchSummaryPayload(BaseModel):
    """Consolidated search export with per-query sections and unique hits."""

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    symbol: JsonValue
    score_threshold: float | None = None
    metadata_filters: JsonDict = Field(default_factory=dict)
    total_queries: int
    total_unique_results: int
    queries: list[SearchQuerySectionPayload] = Field(default_factory=list)
    unique_results: list[SearchUniqueResultPayload] = Field(
        default_factory=list
    )


class SearchOutputPayload(BaseModel):
    """Root payload for analyze search exports."""

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    query: JsonValue
    symbol: JsonValue
    results_count: int
    score_threshold: float | None = None
    metadata_filters: JsonDict = Field(default_factory=dict)
    stats: SearchStatsPayload
    highlights: SearchHighlightsPayload
    analysis: SearchAnalysisPayload
    results: list[SearchResultPayload] = Field(default_factory=list)
