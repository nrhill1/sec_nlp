# src/sec_nlp/pipelines/base/pipeline.py
"""Abstract base classes for all pipelines."""

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator

from sec_nlp.core.infra.logger import logger
from sec_nlp.types import ConfigValue, InitSubclassKwargs

from .config import BasePipelineSettings
from .result import BasePipelineResult

__all__: tuple[str, ...] = ("BasePipeline",)

_CLASSVAR_UNSET = "__UNSET__"


class BasePipeline(BaseModel, ABC):
    """
    Abstract base class for all pipeline types.

    This class inherits from BaseModel to leverage Pydantic's
    lifecycle hooks (model_post_init) for clean initialization.

    Subclasses must implement config_model() and result_model(), and
    the config field is validated against config_model().
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validation_error_cause=True,
        defer_build=True,
        frozen=True,
    )

    pipeline_type: ClassVar[str] = _CLASSVAR_UNSET
    description: ClassVar[str] = _CLASSVAR_UNSET

    requires_llm: ClassVar[bool] = False
    requires_vector_db: ClassVar[bool] = False

    config: BasePipelineSettings

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: InitSubclassKwargs) -> None:
        """Validate subclass metadata and declared model types."""
        super().__pydantic_init_subclass__(**kwargs)

        if cls.model_config.get("frozen") is not True:
            raise TypeError(
                f"{cls.__name__} must not override frozen=True from BasePipeline"
            )

        if cls.pipeline_type == _CLASSVAR_UNSET:
            raise AttributeError(
                f"{cls.__name__} must define 'pipeline_type' ClassVar"
            )

        if cls.description == _CLASSVAR_UNSET:
            raise AttributeError(
                f"{cls.__name__} must define 'description' ClassVar"
            )

    @field_validator("config")
    @classmethod
    def validate_config(
        cls, value: BasePipelineSettings
    ) -> BasePipelineSettings:
        """Ensure config matches the pipeline's config_model."""
        config_model = cls.get_config_model()
        if not isinstance(value, config_model):
            raise ValueError(
                f"A config of type {type(value).__name__} was provided. "
                f"'config' should be of type {config_model.__name__}"
            )
        return value

    def model_post_init(self, __context: dict[str, ConfigValue] | None) -> None:
        """
        Called after Pydantic initialization.
        """
        self._validate_requirements()
        self._build_components()

    def cli_cmd(self) -> BasePipelineResult:
        """Run the pipeline with CliApp.run(<pipeline_class>)"""
        return self.run()

    def _validate_requirements(self) -> None:
        """
        Validate pipeline requirements are met.

        Override this method to add custom requirement validation.
        """
        if self.requires_llm:
            llm_config = getattr(self.config, "llm", None)
            if llm_config is None:
                logger.warning(
                    "%s requires LLM configuration. Set the 'llm' value of the chosen config model to an LLMConfig object",
                    self.pipeline_type,
                )

        if self.requires_vector_db:
            vdb_config = getattr(self.config, "vdb", None)
            if vdb_config is None:
                logger.warning(
                    "%s requires vector DB configuration. Set the 'vdb' value of the chosen config model to a VectorConfig object",
                    self.pipeline_type,
                )

    @abstractmethod
    def run(self) -> BasePipelineResult:
        """
        Execute the pipeline.

        Returns:
            Result object with outputs and metadata
        """

    @abstractmethod
    def _build_components(self) -> None:
        """
        Build pipeline components that depend on config.
        """

    @classmethod
    @abstractmethod
    def config_model(cls) -> type[BasePipelineSettings]:
        """Return the configuration class for this pipeline."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def result_model(cls) -> type[BasePipelineResult]:
        """Return the result class for this pipeline."""
        raise NotImplementedError

    @classmethod
    def get_config_model(cls) -> type[BasePipelineSettings]:
        """
        Get the config class for this pipeline type.

        Returns:
            The configuration class.

        Raises:
            NotImplementedError: If config_model() is not implemented.
        """
        return cls.config_model()

    @classmethod
    def get_result_model(cls) -> type[BasePipelineResult]:
        """
        Get the result class for this pipeline type.

        Returns:
            The result class.

        Raises:
            NotImplementedError: If result_model() is not implemented.
        """
        return cls.result_model()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} type={self.pipeline_type}>"
