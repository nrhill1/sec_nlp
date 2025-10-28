import abc
from pathlib import Path
from typing import Literal

from _typeshed import Incomplete

from sec_nlp.pipelines.base import BasePipeline as BasePipeline
from sec_nlp.pipelines.base import BasePipelineConfig as BasePipelineConfig

class EmbeddingConfig(BasePipelineConfig):
    model_config: Incomplete
    pipeline_type: Literal['embedding']
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

class EmbeddingPipeline(BasePipeline, metaclass=abc.ABCMeta): ...
