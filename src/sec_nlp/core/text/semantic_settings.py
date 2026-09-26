# src/sec_nlp/core/text/semantic_settings.py
"""Shared semantic chunking settings used across pipeline configs.

The settings model is lightweight and pipeline-agnostic so every preset can
expose one consistent semantic chunking surface. Pipelines that perform text
chunking can opt into these controls without redefining per-pipeline fields.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SemanticChunkingSettings(BaseModel):
    """Define shared semantic chunking controls for all pipelines.

    Attributes:
        enabled: Toggle semantic chunking for chunk-producing stages.
        embedding_model: Ollama embedding model used for semantic boundaries.
        embedding_base_url: Optional explicit Ollama base URL override.
        similarity_threshold: Legacy 0-1 threshold mapped to breakpoint amount.
        breakpoint_threshold_type: Experimental breakpoint strategy.
        breakpoint_threshold_amount: Optional explicit breakpoint amount.
        buffer_size: Sentence buffer size for boundary comparisons.
        number_of_chunks: Optional target number of output chunks.
        sentence_split_regex: Regex used for sentence segmentation.
        min_chunk_size: Optional minimum chunk size in characters.
        add_start_index: Include source start offsets in chunk metadata.
        max_chunk_tokens: Optional approximate maximum tokens per chunk.
        min_chunk_sentences: Minimum sentence count for post-processing.
        max_chunk_sentences: Maximum sentence count for post-processing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    enabled: bool = Field(
        default=False,
        description="Enable semantic chunking for chunk-producing stages.",
    )
    embedding_model: str = Field(
        default="granite-embedding:30m",
        description="Ollama embedding model used for semantic chunking.",
    )
    embedding_base_url: str | None = Field(
        default=None,
        description="Optional explicit Ollama base URL for embeddings.",
    )
    similarity_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Legacy 0-1 threshold mapped to experimental breakpoint amount."
        ),
    )
    breakpoint_threshold_type: Literal[
        "percentile",
        "standard_deviation",
        "interquartile",
        "gradient",
    ] = Field(
        default="percentile",
        description="Experimental breakpoint strategy for semantic chunking.",
    )
    breakpoint_threshold_amount: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Optional explicit breakpoint amount. When omitted, "
            "similarity_threshold is mapped automatically."
        ),
    )
    buffer_size: int = Field(
        default=2,
        ge=1,
        description="Sentence buffer size used by semantic chunking.",
    )
    number_of_chunks: int | None = Field(
        default=None,
        ge=1,
        description="Optional target number of semantic chunks.",
    )
    sentence_split_regex: str = Field(
        default=r"(?<=[.?!])\s+",
        description="Regex pattern used for sentence segmentation.",
    )
    min_chunk_size: int | None = Field(
        default=None,
        ge=1,
        description="Optional minimum semantic chunk size in characters.",
    )
    add_start_index: bool = Field(
        default=False,
        description="Include start index metadata when supported.",
    )
    max_chunk_tokens: int | None = Field(
        default=384,
        ge=1,
        description=(
            "Optional approximate maximum tokens per semantic chunk after "
            "local post-processing."
        ),
    )
    min_chunk_sentences: int = Field(
        default=3,
        ge=1,
        description="Minimum sentences per chunk after post-processing.",
    )
    max_chunk_sentences: int = Field(
        default=50,
        ge=1,
        description="Maximum sentences per chunk after post-processing.",
    )
