from pathlib import Path
from typing import Literal

from pydantic import Field, SettingsConfigDict, field_validator

from sec_nlp.pipelines.base import BasePipeline, BasePipelineConfig


class EmbeddingConfig(BasePipelineConfig):
    """Configuration for document embedding pipeline."""

    model_config = SettingsConfigDict(
        env_prefix="EMBEDDING_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    pipeline_type: Literal["embedding"] = "embedding"

    # Input options
    documents_path: Path = Field(
        ...,
        description="Path to documents directory",
    )
    collection_name: str = Field(
        ...,
        description="Qdrant collection name for embeddings",
        min_length=1,
    )

    # Embedding options
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="HuggingFace embedding model name",
    )
    batch_size: int = Field(
        default=32,
        ge=1,
        le=256,
        description="Batch size for embedding generation",
    )
    overwrite: bool = Field(
        default=False,
        description="Overwrite existing collection if it exists",
    )

    @field_validator("documents_path")
    @classmethod
    def validate_documents_path(cls, v: Path) -> Path:
        """Validate documents path exists."""
        if not v.exists():
            raise ValueError(f"Documents path not found: {v}")
        return v

    @field_validator("collection_name")
    @classmethod
    def validate_collection_name(cls, v: str) -> str:
        """Validate collection name is valid."""
        v = v.strip()
        if not v:
            raise ValueError("collection_name must be non-empty")
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("collection_name must be alphanumeric with hyphens/underscores")
        return v

    def validate_config(self) -> None:
        """Validate pipeline-specific configuration."""
        if not self.documents_path.is_dir():
            raise ValueError("documents_path must be a directory")


class EmbeddingPipeline(BasePipeline): ...
