from typing import Any, ClassVar

from _typeshed import Incomplete
from pydantic import BaseModel

from sec_nlp.core import get_logger as get_logger
from sec_nlp.pipelines.base import BaseConfig as BaseConfig
from sec_nlp.pipelines.base import BasePipeline as BasePipeline
from sec_nlp.pipelines.base import C as C
from sec_nlp.pipelines.base import R as R

logger: Incomplete

class PipelineInfo(BaseModel):
    type_id: str
    class_name: str
    description: str
    requires_llm: bool
    requires_vector_db: bool
    module: str
    @classmethod
    def validate_type(cls, v: str) -> str: ...

class PipelineRegistry(BaseModel):
    _pipelines: ClassVar[dict[str, type[BasePipeline[Any]]]]
    _info: ClassVar[dict[str, PipelineInfo]]
    @classmethod
    def register(cls, pipeline_type: str) -> Any: ...
    @classmethod
    def get(cls, pipeline_type: str) -> type[BasePipeline[C, R]]: ...
    @classmethod
    def get_info(cls, pipeline_type: str) -> PipelineInfo: ...
    @classmethod
    def get_all(cls) -> dict[str, type[BasePipeline[C, R]]]: ...
    @classmethod
    def get_all_info(cls) -> dict[str, PipelineInfo]: ...
    @classmethod
    def list_types(cls) -> list[str]: ...
    @classmethod
    def to_dict(cls) -> dict[str, Any]: ...
    @classmethod
    def validate_requirements(cls, pipeline_type: str) -> dict[str, bool]: ...
    @classmethod
    def get_config_class(cls, pipeline_type: str) -> type[BaseConfig]: ...
