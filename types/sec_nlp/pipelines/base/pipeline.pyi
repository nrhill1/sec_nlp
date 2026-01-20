import abc
from abc import ABC, abstractmethod
from typing import ClassVar

from _typeshed import Incomplete
from pydantic import BaseModel

from sec_nlp.types import ConfigValue, InitSubclassKwargs

from .config import BasePipelineSettings
from .result import BasePipelineResult

__all__ = ["BasePipeline"]

class BasePipeline(BaseModel, ABC, metaclass=abc.ABCMeta):
    model_config: Incomplete
    pipeline_type: ClassVar[str]
    description: ClassVar[str]
    requires_llm: ClassVar[bool]
    requires_vector_db: ClassVar[bool]
    config: BasePipelineSettings
    @classmethod
    def __pydantic_init_subclass__(
        cls, **kwargs: InitSubclassKwargs
    ) -> None: ...
    @classmethod
    def validate_config(
        cls, value: BasePipelineSettings
    ) -> BasePipelineSettings: ...
    def model_post_init(
        self, /, __context: dict[str, ConfigValue] | None
    ) -> None: ...
    def cli_cmd(self) -> BasePipelineResult: ...
    @abstractmethod
    def run(self) -> BasePipelineResult: ...
    @classmethod
    @abstractmethod
    def config_model(cls) -> type[BasePipelineSettings]: ...
    @classmethod
    @abstractmethod
    def result_model(cls) -> type[BasePipelineResult]: ...
    @classmethod
    def get_config_model(cls) -> type[BasePipelineSettings]: ...
    @classmethod
    def get_result_model(cls) -> type[BasePipelineResult]: ...
