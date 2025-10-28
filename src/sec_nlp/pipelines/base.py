# sec_nlp/pipelines/base.py
"""Abstract base classes for all pipelines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, Generic, Literal, TypeVar

from pydantic import (
    BaseModel,
    BaseSettings,
    Field,
    SettingsConfigDict,
    computed_field,
    field_validator,
)

from sec_nlp.core import get_logger

logger = get_logger(__name__)


class BaseConfig(BaseSettings):
    """
    Base configuration for all pipeline types.

    Inherits from BaseSettings to support loading defaults from
    environment variables while still accepting explicit CLI arguments.
    """

    model_config = SettingsConfigDict(
        env_prefix="PIPELINE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
        validate_default=True,
        validate_assignment=True,
        cli_parse_args=True,
    )

    pipeline_type: str

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


class BaseResult(ABC, BaseModel):
    """Base result type for all pipelines."""

    success: bool
    pipeline_type: str
    outputs: list[Path] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    @computed_field
    @property
    def has_outputs(self) -> bool:
        """Check if pipeline produced any outputs."""
        return len(self.outputs) > 0


# Pipeline Generics
C = TypeVar("C", bound=BaseConfig)  # Config
R = TypeVar("R", bound=BaseResult)  # Result


class BasePipeline(ABC, BaseModel, Generic[C, R]):
    """Abstract base class for all pipeline types."""

    config: C
    result: R

    pipeline_type: ClassVar[str]
    description: ClassVar[str]

    requires_llm: ClassVar[bool] = False
    requires_vector_db: ClassVar[bool] = False

    def __init__(self, config: C) -> None:
        """Initialize pipeline with validated config."""
        self.config = config
        self._validate_requirements()

    @abstractmethod
    def run(self, **kwargs: Any) -> R:
        """
        Execute the pipeline.

        Returns:
            BaseResult with outputs and metadata
        """
        pass

    @abstractmethod
    def validate_inputs(self) -> None:
        """Validate that all required inputs are available."""
        pass

    def _validate_requirements(self) -> None:
        """Validate pipeline requirements are met."""
        pass

    @classmethod
    def get_config_class(cls) -> type[C]:
        """Get the config class for this pipeline type."""
        orig_bases = getattr(cls, "__orig_bases__", ())
        for base in orig_bases:
            if hasattr(base, "__args__"):
                return base.__args__[0]
        raise TypeError(f"Could not determine config class for {cls.__name__}")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} type={self.pipeline_type}>"
