# src/sec_nlp/pipelines/base/result.py
"""Base result types for pipelines."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.types import InitSubclassKwargs, JsonObject, ResultDict

_CLASSVAR_UNSET = "__UNSET__"

type SummaryFieldValue = str | bool | int | float | None


class BasePipelineResult(BaseModel, ABC):
    """Base result type for all pipelines."""

    pipeline_type: ClassVar[str] = _CLASSVAR_UNSET

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="ignore",
        defer_build=True,
        validation_error_cause=True,
        use_attribute_docstrings=False,
        frozen=True,
    )

    success: bool = Field(
        default=True,
        description="Whether or not the operation was successful",
    )
    outputs: list[Path] = Field(
        default_factory=list,
        description="A list of Path objects containing the locations of output files",
    )
    metadata: ResultDict = Field(
        default_factory=dict,
        description="A dictionary containing metadata related to the output",
    )
    error: str | None = Field(
        default=None,
        description="A string containing an error message (if an error occurred.)",
    )
    raw_output: str | None = Field(
        default=None,
        description="A string containing the raw output (LLM, etc.), usually upon an unsuccessful operation.",
    )

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: InitSubclassKwargs) -> None:
        """Ensure pipeline_type is set and frozen is not overridden."""
        super().__pydantic_init_subclass__(**kwargs)

        if cls.pipeline_type == _CLASSVAR_UNSET:
            raise TypeError(
                f"{cls.__name__} must set 'pipeline_type' ClassVar to a non-default value"
            )

        if cls.model_config.get("frozen") is not True:
            raise TypeError(
                f"{cls.__name__} must not override frozen=True from BasePipelineResult"
            )

    @abstractmethod
    def summary_fields(self) -> JsonObject:
        """Return a short mapping for result summaries."""
        raise NotImplementedError

    def base_summary_fields(self) -> dict[str, SummaryFieldValue]:
        """Return common summary fields shared across result models."""
        return {
            "pipeline": self.pipeline_type,
            "success": self.success,
            "outputs": len(self.outputs),
            "error": self.error,
        }

    def is_success(self) -> bool:
        """Check if pipeline execution was successful."""
        return self.success and not self.error

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} type={self.pipeline_type} success={self.success}>"

    def __str__(self) -> str:
        """Get human-readable result summary."""
        status = "✓ Success" if self.is_success() else "✗ Failed"
        parts = [f"{status}: {self.pipeline_type}"]

        if self.outputs:
            parts.append(f"  Outputs: {len(self.outputs)} files")

        if self.metadata:
            parts.append(f"  Metadata: {len(self.metadata)} items")

        if self.error:
            parts.append(f"  Error: {self.error}")

        return "\n".join(parts)

    @property
    def num_outputs(self) -> int:
        """Get number of output files generated."""
        return len(self.outputs)

    def print_summary(self) -> None:
        """Print result summary to console."""
        print(str(self))
