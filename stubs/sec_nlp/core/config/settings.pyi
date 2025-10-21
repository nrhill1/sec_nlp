from functools import lru_cache
from pathlib import Path
from typing import Literal

from _typeshed import Incomplete
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    model_config: Incomplete
    email: str
    qdrant_host: str
    qdrant_port: int
    qdrant_grpc_port: int
    qdrant_api_key: str | None
    qdrant_url: str | None
    qdrant_prefer_grpc: bool
    qdrant_https: bool
    qdrant_timeout: int
    qdrant_collection_prefix: str
    qdrant_distance: Literal["Cosine", "Euclid", "Dot"]
    qdrant_vector_size: int | None
    qdrant_on_disk_payload: bool
    qdrant_replication_factor: int
    qdrant_write_consistency_factor: int
    embedding_model: str
    embedding_device: Literal["cpu", "cuda", "mps"]
    embedding_batch_size: int
    ollama_base_url: str
    ollama_timeout: int
    hf_home: Path | None
    transformers_cache: Path | None
    transformers_offline: bool
    log_level: str
    log_format: Literal["simple", "detailed", "json"]
    environment: Literal["development", "production", "test"]
    @classmethod
    def validate_log_level(cls, v: str) -> str: ...
    @property
    def is_production(self) -> bool: ...
    @property
    def is_development(self) -> bool: ...
    @property
    def is_test(self) -> bool: ...
    @property
    def qdrant_connection_url(self) -> str: ...

@lru_cache
def _get_settings() -> Settings: ...

settings: Incomplete
