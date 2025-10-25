# sec_nlp/core/config/settings.py
"""Centralized application settings using Pydantic."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Usage:
        from sec_nlp.core.config import settings

        print(settings.email)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # SEC API
    email: str = Field(
        default="user@example.com",
        description="Email for SEC EDGAR API (required by SEC)",
        alias="email",
    )

    # Qdrant Vector Database
    qdrant_host: str = Field(
        default="localhost", description="Qdrant server host", alias="qdrant_host"
    )
    qdrant_port: int = Field(
        default=6333, description="Qdrant server port", ge=1, le=65535, alias="qdrant_port"
    )
    qdrant_grpc_port: int = Field(
        default=6334,
        description="Qdrant gRPC port (for better performance)",
        ge=1,
        le=65535,
        alias="qdrant_grpc_port",
    )
    qdrant_api_key: str | None = Field(
        default=None,
        description="Qdrant API key (for Qdrant Cloud or secured instances)",
        alias="qdrant_api_key",
    )
    qdrant_url: str | None = Field(
        default=None, description="Full Qdrant URL (overrides host/port if set)", alias="qdrant_url"
    )
    qdrant_prefer_grpc: bool = Field(
        default=False,
        description="Use gRPC instead of REST API for better performance",
        alias="qdrant_prefer_grpc",
    )
    qdrant_https: bool = Field(
        default=False, description="Use HTTPS for Qdrant connection", alias="qdrant_https"
    )
    qdrant_timeout: int = Field(
        default=60, description="Qdrant request timeout in seconds", ge=1, alias="qdrant_timeout"
    )

    # Qdrant Collection Settings
    qdrant_collection_prefix: str = Field(
        default="sec_nlp",
        description="Prefix for Qdrant collection names",
        alias="qdrant_collection_prefix",
    )
    qdrant_distance: Literal["Cosine", "Euclid", "Dot"] = Field(
        default="Cosine",
        description="Distance metric for vector similarity",
        alias="qdrant_distance",
    )
    qdrant_vector_size: int | None = Field(
        default=None,
        description="Vector dimension (auto-inferred from embedding model if not set)",
        alias="qdrant_vec_size",
    )
    qdrant_on_disk_payload: bool = Field(
        default=False,
        description="Store payload on disk to save RAM",
        alias="qdrant_on_disk_payload",
    )
    qdrant_replication_factor: int = Field(
        default=1,
        description="Number of replicas for each shard (Qdrant Cloud)",
        ge=1,
        alias="qdrant_replication_factor",
    )
    qdrant_write_consistency_factor: int = Field(
        default=1,
        description="Minimum number of replicas to confirm write",
        ge=1,
        alias="qdrant_write_consistency_factor",
    )

    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Hugging Face embedding model name",
        alias="embedding_model",
    )
    embedding_device: Literal["cpu", "cuda", "mps"] = Field(
        default="cpu", description="Device for embedding model", alias="embedding_device"
    )
    embedding_batch_size: int = Field(
        default=32,
        description="Batch size for embedding generation",
        ge=1,
        alias="embedding_batch_size",
    )

    # Ollama
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama server base URL",
        alias="ollama_base_url",
    )
    ollama_timeout: int = Field(
        default=120, description="Ollama request timeout in seconds", ge=1, alias="ollama_timeout"
    )

    # Hugging Face
    hf_cache: Path | None = Field(
        default=None, description="Hugging Face cache directory", alias="hf_cache"
    )
    transformers_cache: Path | None = Field(
        default=None, description="Transformers model cache directory", alias="transformers_cache"
    )

    # Application
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        alias="log_level",
    )
    log_format: Literal["simple", "detailed", "json"] = Field(
        default="simple", description="Log output format", alias="log_format"
    )
    environment: Literal["development", "production", "test"] = Field(
        default="development", description="Application environment", alias="environment"
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v_upper

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"

    @property
    def is_test(self) -> bool:
        """Check if running in test environment."""
        return self.environment == "test"

    @property
    def qdrant_connection_url(self) -> str:
        """Get the full Qdrant connection URL."""
        if self.qdrant_url:
            return self.qdrant_url

        protocol = "https" if self.qdrant_https else "http"
        return f"{protocol}://{self.qdrant_host}:{self.qdrant_port}"


@lru_cache
def _get_settings() -> Settings:
    """
    Get cached settings instance.

    This function is cached to ensure we only load settings once.

    Returns:
        Singleton Settings instance
    """
    return Settings()


# Singleton instance for convenient import
settings = _get_settings()
