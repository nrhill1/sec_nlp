import abc

from pydantic import BaseModel

from sec_nlp.pipelines.base import BasePipeline as BasePipeline
from sec_nlp.pipelines.base import BaseResult as BaseResult

from .config import EmbeddingConfig as EmbeddingConfig

class EmbeddingInput(BaseModel): ...
class EmbeddingResult(BaseResult): ...
class EmbeddingPipeline(
    BasePipeline[EmbeddingConfig, EmbeddingInput, EmbeddingResult],
    metaclass=abc.ABCMeta,
): ...
