"""Typed handoff artifacts from retrieve to downstream pipelines."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RetrieveChatSeedChunk(BaseModel):
    """Single retrieve hit payload optimized for chat handoff."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    collection: str = Field(
        default="retrieve",
        description="Collection name to attribute this chunk to.",
    )
    symbol: str | None = Field(
        default=None,
        description="Ticker symbol associated with the chunk.",
    )
    accession_number: str | None = Field(
        default=None,
        description="SEC accession identifier.",
    )
    form_type: str | None = Field(
        default=None,
        description="SEC form type for the source filing.",
    )
    filed_date: str | None = Field(
        default=None,
        description="Filing date in YYYY-MM-DD format.",
    )
    source: str | None = Field(
        default=None,
        description="Canonical source URL for this chunk.",
    )
    score: float = Field(
        default=0.0,
        description="Retrieval score used for ordering.",
    )
    snippet: str = Field(
        default="",
        description="Chunk text snippet for grounded chat responses.",
    )


class RetrieveChatSeedBundle(BaseModel):
    """Batch of retrieve chunks passed directly into chat execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(
        description="Retrieve run UUID that produced this bundle.",
    )
    run_short_id: int | None = Field(
        default=None,
        description="Retrieve short run ID when available.",
    )
    symbols: list[str] = Field(
        default_factory=list,
        description="Symbols represented in this bundle.",
    )
    queries: list[str] = Field(
        default_factory=list,
        description="Queries used to produce these chunks.",
    )
    chunks: list[RetrieveChatSeedChunk] = Field(
        default_factory=list,
        description="Flattened ranked chunks across processed symbols.",
    )
