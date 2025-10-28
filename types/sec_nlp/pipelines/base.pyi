import abc
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, Generic, Literal, TypeVar

from _typeshed import Incomplete
from pydantic import BaseModel, BaseSettings, computed_field

from sec_nlp.core import get_logger as get_logger

logger: Incomplete

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

class BaseResult(ABC, BaseModel):
    success: bool
    pipeline_type: str
    outputs: list[Path]
    metadata: dict[str, Any]
    error: str | None
    @computed_field
    @property
    def has_outputs(self) -> bool: ...

C = TypeVar("C", bound=BaseConfig)
R = TypeVar("R", bound=BaseResult)

class BasePipeline(ABC, BaseModel, Generic[C, R], metaclass=abc.ABCMeta):
    config: C
    result: R
    pipeline_type: ClassVar[str]
    description: ClassVar[str]
    requires_llm: ClassVar[bool]
    requires_vector_db: ClassVar[bool]
    def __init__(self, config: C) -> None: ...
    @abstractmethod
    def run(self, **kwargs: Any) -> R: ...
    @abstractmethod
    def validate_inputs(self) -> None: ...
    def _validate_requirements(self) -> None: ...
    @classmethod
    def get_config_class(cls) -> type[C]: ...
    def __repr__(self) -> str: ...
