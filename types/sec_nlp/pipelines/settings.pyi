from pathlib import Path
from typing import Literal

from pydantic import BaseModel

class LLMSettings(BaseModel):
    model_name: str
    prompt_file: Path | None
    max_new_tokens: int
    temperature: float
    require_json: bool
    @classmethod
    def validate_prompt_file(cls, v: Path | None) -> Path | None: ...

class VectorDBSettings(BaseModel):
    collection_name: str | None
    embedding_model: str
    embedding_device: str
    embedding_batch_size: int
    vector_size: int | None
    qdrant_url: str | None
    qdrant_host: str
    qdrant_port: int
    qdrant_grpc_port: int
    qdrant_api_key: str | None
    qdrant_https: bool
    qdrant_prefer_grpc: bool
    qdrant_timeout: int
    qdrant_distance: Literal['Cosine', 'Euclid', 'Dot']
    qdrant_on_disk_payload: bool
    qdrant_replication_factor: int
    qdrant_write_consistency_factor: int
