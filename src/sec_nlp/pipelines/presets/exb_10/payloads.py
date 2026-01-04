"""Payload models for Exhibit 10 search exports."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.types import JsonValue


class SearchRecordPayload(BaseModel):
    """Optional fields for Exhibit 10 search records."""

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    query: JsonValue | None = None
    query_slug: JsonValue | None = None
    output_file: JsonValue | None = None
    num_results: int | None = None
    top_symbols: list[JsonValue] | None = None


class SearchManifestMetaPayload(BaseModel):
    """Metadata for Exhibit 10 search manifests."""

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    run_id: JsonValue
    timestamp: JsonValue
    pipeline_type: JsonValue
    search_type: JsonValue
    collection: JsonValue
    total_queries: int
    total_results: int


class SearchManifestPayload(BaseModel):
    """Root payload for Exhibit 10 search manifests."""

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    meta: SearchManifestMetaPayload
    queries: list[SearchRecordPayload] = Field(default_factory=list)
