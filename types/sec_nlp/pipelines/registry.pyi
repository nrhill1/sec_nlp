from typing import Any, ClassVar

from _typeshed import Incomplete
from pydantic import BaseModel

from sec_nlp.core import get_logger as get_logger
from sec_nlp.pipelines.base import BaseConfig as BaseConfig
from sec_nlp.pipelines.base import BasePipeline as BasePipeline
from sec_nlp.pipelines.base import BaseResult as BaseResult

logger: Incomplete
PipelineType = type[BasePipeline[BaseConfig, BaseModel, BaseResult]]

class PipelineRegistry(BaseModel):
    _pipelines: ClassVar[dict[str, PipelineType]]
    @classmethod
    def register(cls, pipeline_type: str) -> Any: ...
    @classmethod
    def get_pipeline(cls, pipeline_type: str) -> PipelineType: ...
    @classmethod
    def get_all_pipelines(cls) -> list[PipelineType]: ...
    @classmethod
    def list_types(cls) -> list[str]: ...
    @classmethod
    def get_pipeline_config_class(
        cls, pipeline_type: str
    ) -> type[BaseConfig]: ...
