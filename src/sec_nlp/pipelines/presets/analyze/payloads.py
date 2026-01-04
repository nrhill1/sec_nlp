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
