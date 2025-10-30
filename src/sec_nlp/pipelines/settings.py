# src/sec_nlp/pipelines/config.py
"""Extensions of BaseConfig and models for specific groups of settings (LLMs, Vector DBs, etc.)"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)


class LLMSettings(BaseModel):
    """Configuration for LLM settings."""

    model_name: str = Field(
        default="google/flan-t5-base",
        description="LLM model name (HuggingFace or 'ollama:model-name')",
    )
    prompt_file: Path | None = Field(
        default=None,
        description="Path to custom prompt YAML file",
    )
    max_new_tokens: int = Field(
        default=1024,
        ge=1,
        le=8192,
        description="Maximum tokens for LLM generation",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Temperature for LLM sampling",
    )
    require_json: bool = Field(
        default=True,
        description="Require JSON-formatted output from LLM",
    )

    @field_validator("prompt_file", mode="after")
    @classmethod
    def validate_prompt_file(cls, v: Path | None) -> Path | None:
        """Validate prompt file exists if provided."""
        if v is not None and not v.exists():
            raise ValueError(f"Prompt file not found: {v}")
        return v


class VectorDBSettings(BaseModel):
    """Configuration for vector database settings."""

    # Collection settings
    collection_name: str | None = Field(
        default=None,
        description="Name prefix for vector database collections",
    )

    # Embedding settings
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        description="Sentence transformer model for embeddings",
    )
    embedding_device: str = Field(
        default="cpu",
        description="Device for embedding model (cpu, cuda, mps)",
    )
    embedding_batch_size: int = Field(
        default=32,
        ge=1,
        description="Batch size for embedding generation",
    )
    vector_size: int | None = Field(
        default=None,
        ge=1,
        description="Dimension of embedding vectors (auto-detected if None)",
    )

    # Qdrant settings
    qdrant_url: str | None = Field(
        default=None,
        description="Qdrant server URL (e.g., 'http://localhost:6333')",
    )
    qdrant_host: str = Field(
        default="localhost",
        description="Qdrant server host",
    )
    qdrant_port: int = Field(
        default=6333,
        ge=1,
        le=65535,
        description="Qdrant HTTP port",
    )
    qdrant_grpc_port: int = Field(
        default=6334,
        ge=1,
        le=65535,
        description="Qdrant gRPC port",
    )
    qdrant_api_key: str | None = Field(
        default=None,
        description="Qdrant API key for authentication",
    )
    qdrant_https: bool = Field(
        default=False,
        description="Use HTTPS for Qdrant connection",
    )
    qdrant_prefer_grpc: bool = Field(
        default=False,
        description="Prefer gRPC over HTTP",
    )
    qdrant_timeout: int = Field(
        default=60,
        ge=1,
        description="Qdrant request timeout in seconds",
    )

    # Collection configuration
    qdrant_distance: Literal["Cosine", "Euclid", "Dot"] = Field(
        default="Cosine",
        description="Distance metric for vector similarity",
    )
    qdrant_on_disk_payload: bool = Field(
        default=False,
        description="Store payload on disk to save RAM",
    )
    qdrant_replication_factor: int = Field(
        default=1,
        ge=1,
        description="Number of replicas for the collection",
    )
    qdrant_write_consistency_factor: int = Field(
        default=1,
        ge=1,
        description="Write consistency factor",
    )
