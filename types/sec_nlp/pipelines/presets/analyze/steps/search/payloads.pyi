from _typeshed import Incomplete
from pydantic import BaseModel

from sec_nlp.types import (
    JsonDict as JsonDict,
    JsonValue as JsonValue,
)

class SearchStatsPayload(BaseModel):
    model_config: Incomplete
    average_score: float | None
    best_score: float | None
    symbols: JsonDict
    sections: JsonDict
    tag_frequency: JsonDict
    sentiment_breakdown: JsonDict

class SearchHighlightsPayload(BaseModel):
    model_config: Incomplete
    top_summaries: list[str]

class SearchAnalysisResultPayload(BaseModel):
    model_config: Incomplete
    is_relevant: bool | None
    confidence_score: float | None
    summary: JsonValue | None
    key_points: list[JsonValue] | None
    reasoning: JsonValue | None
    tags: list[JsonValue] | None
    sentiment: JsonValue | None
    severity: JsonValue | None
    forward_looking: bool | None
    evidence_spans: list[JsonDict] | None
    source_excerpt: JsonValue | None
    extracted_entities: JsonDict | None
    follow_up_questions: list[JsonValue] | None
    source_metadata: JsonDict | None
    raw_chunk: JsonValue | None
    error: JsonValue | None
    exception: JsonValue | None
    chunk_preview: JsonValue | None

class SearchAnalysisPayload(BaseModel):
    model_config: Incomplete
    enabled: bool
    analyzed_hits: int
    results: list[SearchAnalysisResultPayload]

class SearchResultPayload(BaseModel):
    model_config: Incomplete
    score: float
    content: JsonValue
    metadata: JsonDict
    summary: JsonValue | None
    tags: JsonValue | None
    sentiment: JsonValue | None
    forward_looking: bool | None
    confidence_score: float | None

class SearchMatchPayload(BaseModel):
    model_config: Incomplete
    query: JsonValue
    score: float

class SearchQuerySectionPayload(BaseModel):
    model_config: Incomplete
    query: JsonValue
    results_count: int
    stats: SearchStatsPayload
    highlights: SearchHighlightsPayload
    results: list[SearchResultPayload]

class SearchUniqueResultPayload(BaseModel):
    model_config: Incomplete
    content: JsonValue
    metadata: JsonDict
    matched_queries: list[SearchMatchPayload]
    best_score: float | None

class SearchSummaryPayload(BaseModel):
    model_config: Incomplete
    symbol: JsonValue
    score_threshold: float | None
    metadata_filters: JsonDict
    total_queries: int
    total_unique_results: int
    queries: list[SearchQuerySectionPayload]
    unique_results: list[SearchUniqueResultPayload]

class SearchOutputPayload(BaseModel):
    model_config: Incomplete
    query: JsonValue
    symbol: JsonValue
    results_count: int
    score_threshold: float | None
    metadata_filters: JsonDict
    stats: SearchStatsPayload
    highlights: SearchHighlightsPayload
    analysis: SearchAnalysisPayload
    results: list[SearchResultPayload]
