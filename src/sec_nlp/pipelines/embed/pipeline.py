# src/sec_nlp/pipelines/embed/pipeline.py
from pydantic import BaseModel

from sec_nlp.pipelines.base import BasePipeline, BaseResult

from .config import EmbeddingConfig


class EmbeddingInput(BaseModel): ...


class EmbeddingResult(BaseResult): ...


class EmbeddingPipeline(BasePipeline[EmbeddingConfig, EmbeddingResult]): ...
