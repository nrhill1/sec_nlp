import abc
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, Generic, Literal, TypeVar

from _typeshed import Incomplete
from pydantic import BaseModel, computed_field
from pydantic_settings import BaseSettings

from sec_nlp.core import get_logger as get_logger

logger: Incomplete

class BaseResult(BaseModel):
    pipeline_type: ClassVar[str]
    model_config: Incomplete
    success: bool
    outputs: list[Path]
    metadata: dict[str, Any]
    error: str | None
    raw_output: str | None
    @computed_field
    @property
    def has_outputs(self) -> bool: ...

class BaseConfig(BaseSettings):
    model_config: Incomplete
    pipeline_type: str
    verbose: bool
    dry_run: bool
    log_format: Literal["simple", "detailed", "json"]
    log_file: Path | None
    def get_log_level(self) -> str: ...
    @classmethod
    def validate_log_file(cls, v: Path | None) -> Path | None: ...

C = TypeVar("C", bound=BaseConfig)
I = TypeVar("I", bound=BaseModel)
R = TypeVar("R", bound=BaseResult)

class BasePipeline(ABC, BaseModel, Generic[C, I, R], metaclass=abc.ABCMeta):
    _config_class: ClassVar[type[C]]
    _input_class: ClassVar[type[I]]
    _result_class: ClassVar[type[R]]
    config: C
    model_config: Incomplete
    pipeline_type: ClassVar[str]
    description: ClassVar[str]
    requires_llm: ClassVar[bool]
    requires_vector_db: ClassVar[bool]
    def __init__(self, config: C, **kwargs: Any) -> None: ...
    def model_post_init(self, /, __context: Any) -> None: ...
    def _build_components(self) -> None: ...
    @abstractmethod
    def run(self, *args, **kwargs) -> R: ...
    @abstractmethod
    def validate_inputs(self, input_data: I) -> None: ...
    def _validate_requirements(self) -> None: ...
    @classmethod
    def get_config_class(cls) -> type[C]: ...
    @classmethod
    def get_input_class(cls) -> type[I]: ...
    @classmethod
    def get_result_class(cls) -> type[R]: ...
    def __repr__(self) -> str: ...
