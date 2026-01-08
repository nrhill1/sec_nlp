import abc
from abc import ABC, abstractmethod
from typing import ClassVar

from _typeshed import Incomplete
from pydantic import BaseModel

from sec_nlp.types import ConfigValue, InitSubclassKwargs

from .config import BaseConfig
from .result import BaseResult

__all__ = ["BasePipeline"]

class BasePipeline(BaseModel, ABC, metaclass=abc.ABCMeta):
    model_config: Incomplete
    pipeline_type: ClassVar[str]
    description: ClassVar[str]
    requires_llm: ClassVar[bool]
    requires_vector_db: ClassVar[bool]
    config: BaseConfig
    @classmethod
    def __pydantic_init_subclass__(
        cls, **kwargs: InitSubclassKwargs
    ) -> None: ...
    @classmethod
    def validate_config(cls, value: BaseConfig) -> BaseConfig: ...
    def model_post_init(
        self, /, __context: dict[str, ConfigValue] | None
    ) -> None: ...
    def cli_cmd(self) -> BaseResult: ...
    @abstractmethod
    def run(self) -> BaseResult: ...
    @classmethod
    @abstractmethod
    def config_model(cls) -> type[BaseConfig]: ...
    @classmethod
    @abstractmethod
    def result_model(cls) -> type[BaseResult]: ...
    @classmethod
    def get_config_model(cls) -> type[BaseConfig]: ...
    @classmethod
    def get_result_model(cls) -> type[BaseResult]: ...
