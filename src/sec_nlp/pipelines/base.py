# sec_nlp/pipelines/base.py
"""Abstract base classes for all pipelines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, Generic, Literal, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from sec_nlp.core import get_logger

logger = get_logger(__name__)


class BaseResult(BaseModel):
    """Base result type for all pipelines."""

    pipeline_type: ClassVar[str]

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool = True
    outputs: list[Path] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    raw_output: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_outputs(self) -> bool:
        """Check if pipeline produced any outputs."""
        return len(self.outputs) > 0


class BaseConfig(BaseSettings):
    """Base config type for all pipelines."""

    model_config = SettingsConfigDict(
        extra="allow",
        arbitrary_types_allowed=True,
    )

    pipeline_type: ClassVar[str]

    verbose: bool = Field(
        default=False,
        description="Enable verbose (DEBUG) logging",
    )
    dry_run: bool = Field(
        default=False,
        description="Run without performing any embedding",
    )
    log_format: Literal["simple", "detailed", "json"] = Field(
        default="simple",
        description="Log output format",
    )
    log_file: Path | None = Field(
        default=None,
        description="Write logs to file instead of console",
    )

    def get_log_level(self) -> str:
        """Get computed log level."""
        return "DEBUG" if self.verbose else "INFO"

    @field_validator("log_file", mode="after")
    @classmethod
    def validate_log_file(cls, v: Path | None) -> Path | None:
        """Ensure log file parent directory exists."""
        if v is not None:
            v.parent.mkdir(parents=True, exist_ok=True)
        return v


# Type variables for generic pipeline components
C = TypeVar("C", bound=BaseConfig)  # Config
I = TypeVar("I", bound=BaseModel)  # Input  # noqa: E741
R = TypeVar("R", bound=BaseResult)  # Result


class BasePipeline(ABC, BaseModel, Generic[C, I, R]):
    """
    Abstract base class for all pipeline types.

    This class inherits from BaseModel to leverage Pydantic's
    lifecycle hooks (model_post_init) for clean initialization.

    Type Parameters:
        C: Configuration type (extends BaseConfig)
        I: Input data type (extends BaseModel)
        R: Result type (extends BaseResult)
    """

    _config_class: ClassVar[type[C]]
    _input_class: ClassVar[type[I]]
    _result_class: ClassVar[type[R]]

    config: C

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True,
    )

    pipeline_type: ClassVar[str]
    description: ClassVar[str]
    requires_llm: ClassVar[bool] = False
    requires_vector_db: ClassVar[bool] = False

    def __init__(self, config: C, **kwargs: Any) -> None:
        """
        Initialize pipeline with validated config.

        Args:
            config: Validated configuration object
            **kwargs: Additional fields (if any)
        """
        super().__init__(config=config, **kwargs)

    def model_post_init(self, __context: Any) -> None:
        """
        Called after Pydantic initialization.
        """
        self._validate_requirements()
        self._build_components()

    def _build_components(self) -> None:
        """
        Build pipeline components that depend on config.
        """
        pass

    @abstractmethod
    def run(self, *args, **kwargs) -> R:
        """
        Execute the pipeline.

        Args:
            input_data: Optional input data for the pipeline.
                       Some pipelines may not need input data if they
                       operate based on configuration alone.

        Returns:
            Result object with outputs and metadata
        """
        pass

    @abstractmethod
    def validate_inputs(self, input_data: I) -> None:
        """
        Validate that input data is valid.

        Args:
            input_data: Input data to validate

        Raises:
            ValueError: If input data is invalid
        """
        pass

    def _validate_requirements(self) -> None:
        """
        Validate pipeline requirements are met.

        Override this method to add custom requirement validation.
        """
        if self.requires_llm:
            # Check if config has LLM settings
            if not hasattr(self.config, "llm") or self.config.llm is None:
                logger.warning(
                    f"{self.pipeline_type} requires LLM configuration"
                )

        if self.requires_vector_db:
            # Check if config has vector DB settings
            if not hasattr(self.config, "vdb") or self.config.vdb is None:
                logger.warning(
                    f"{self.pipeline_type} requires vector DB configuration"
                )

    @classmethod
    def get_config_class(cls) -> type[C]:
        """
        Get the config class for this pipeline type.

        Returns:
            The configuration class (C type parameter)

        Raises:
            TypeError: If config class cannot be determined
        """
        return cls._config_class

    @classmethod
    def get_input_class(cls) -> type[I]:
        """
        Get the input class for this pipeline type.

        Returns:
            The input class (I type parameter)

        Raises:
            TypeError: If input class cannot be determined
        """
        return cls._input_class

    @classmethod
    def get_result_class(cls) -> type[R]:
        """
        Get the result class for this pipeline type.

        Returns:
            The result class (R type parameter)

        Raises:
            TypeError: If result class cannot be determined
        """
        return cls._result_class

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} type={self.pipeline_type}>"
