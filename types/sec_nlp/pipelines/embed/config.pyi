from pathlib import Path
from typing import Literal

from _typeshed import Incomplete

from sec_nlp.pipelines.base import BaseConfig as BaseConfig

class EmbeddingConfig(BaseConfig):
    model_config: Incomplete
    pipeline_type: Literal["embedding"]
    documents_path: Path
    collection_name: str
    embedding_model: str
    batch_size: int
    overwrite: bool
    @classmethod
    def validate_documents_path(cls, v: Path) -> Path: ...
    @classmethod
    def validate_collection_name(cls, v: str) -> str: ...
    def validate_config(self) -> None: ...
