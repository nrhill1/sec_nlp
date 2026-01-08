import abc
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from _typeshed import Incomplete
from pydantic import BaseModel

from sec_nlp.types import (
    InitSubclassKwargs as InitSubclassKwargs,
    JsonObject as JsonObject,
    ResultDict as ResultDict,
)

type SummaryFieldValue = str | bool | int | float | None

class BaseResult(BaseModel, ABC, metaclass=abc.ABCMeta):
    pipeline_type: ClassVar[str]
    model_config: Incomplete
    success: bool
    outputs: list[Path]
    metadata: ResultDict
    error: str | None
    raw_output: str | None
    @classmethod
    def __pydantic_init_subclass__(
        cls, **kwargs: InitSubclassKwargs
    ) -> None: ...
    @abstractmethod
    def summary_fields(self) -> JsonObject: ...
    def base_summary_fields(self) -> dict[str, SummaryFieldValue]: ...
    def is_success(self) -> bool: ...
    @property
    def num_outputs(self) -> int: ...
    def print_summary(self) -> None: ...
