"""Typed seeded context models for chat pipeline execution."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ChatSeedChunk(BaseModel):
    """Minimal chunk payload consumed by chat without vector lookup."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    collection: str = Field(
        default="retrieve",
        description="Source collection label for citation provenance.",
    )
    score: float = Field(
        default=0.0,
        description="Precomputed retrieval score used for ranking.",
    )
    symbol: str | None = Field(
        default=None,
        description="Associated symbol if available.",
    )
    accession_number: str | None = Field(
        default=None,
        description="SEC accession identifier.",
    )
    form_type: str | None = Field(
        default=None,
        description="SEC form type for the originating filing.",
    )
    filed_date: str | None = Field(
        default=None,
        description="Filing date in YYYY-MM-DD format.",
    )
    source: str | None = Field(
        default=None,
        description="Source URL for the citation.",
    )
    snippet: str = Field(
        default="",
        description="Snippet text used for prompt context and citations.",
    )


class ChatSeedBundle(BaseModel):
    """Seeded context bundle used to bypass collection search."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    upstream_pipeline: str = Field(
        default="retrieve",
        description="Pipeline that generated this seeded context.",
    )
    upstream_run_id: str = Field(
        description="Upstream run UUID for provenance.",
    )
    upstream_short_id: int | None = Field(
        default=None,
        description="Upstream short run ID when available.",
    )
    symbols: list[str] = Field(
        default_factory=list,
        description="Symbols represented in seeded chunks.",
    )
    queries: list[str] = Field(
        default_factory=list,
        description="Upstream query list used to produce chunks.",
    )
    chunks: list[ChatSeedChunk] = Field(
        default_factory=list,
        description="Seeded chunks available for answer generation.",
    )
