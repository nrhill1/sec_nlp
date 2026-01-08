import abc
from abc import ABC, abstractmethod

from pydantic import BaseModel

from sec_nlp.pipelines.base import BasePipeline

__all__ = ["PipelineCommand"]

class PipelineCommand(BaseModel, ABC, metaclass=abc.ABCMeta):
    @classmethod
    @abstractmethod
    def pipeline_class(cls) -> type[BasePipeline]: ...
    @classmethod
    def __pydantic_init_subclass__(
        cls, **kwargs: bool | str | int | float
    ) -> None: ...
    def cli_cmd(self) -> None: ...
