# src/sec_nlp/pipelines/composition/stage.py
"""Pipeline stage protocol and adapters for composition."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.pipelines.base.config import BasePipelineSettings
from sec_nlp.pipelines.base.pipeline import BasePipeline
from sec_nlp.pipelines.base.result import BasePipelineResult
from sec_nlp.types import ResultDict


class StageOutput(BaseModel):
    """Output from a pipeline stage, used for passing data between stages."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    success: bool = Field(
        description="Whether the stage completed successfully",
    )
    outputs: list[Path] = Field(
        default_factory=list,
        description="Output file paths from the stage",
    )
    metadata: ResultDict = Field(
        default_factory=dict,
        description="Metadata from the stage result",
    )
    error: str | None = Field(
        default=None,
        description="Error message if the stage failed",
    )

    @classmethod
    def from_result(cls, result: BasePipelineResult) -> StageOutput:
        """Create a StageOutput from a pipeline result."""
        return cls(
            success=result.success,
            outputs=list(result.outputs),
            metadata=dict(result.metadata),
            error=result.error,
        )


class PipelineStage(BaseModel):
    """A configured pipeline stage ready for execution.

    This wraps a pipeline class and its configuration, providing
    a uniform interface for the chain executor.
    """

    model_config = ConfigDict(
        frozen=True,
        arbitrary_types_allowed=True,
    )

    name: str = Field(
        description="Human-readable name for this stage",
    )
    pipeline_cls: type[BasePipeline] = Field(
        description="Pipeline class to instantiate and run",
    )
    config: BasePipelineSettings = Field(
        description="Configuration for the pipeline",
    )
    skip_on_failure: bool = Field(
        default=False,
        description="Whether to skip this stage if a previous stage failed",
    )
    condition: Callable[[StageOutput | None], bool] | None = Field(
        default=None,
        description="Optional condition function to determine if stage should run",
    )

    def should_run(self, previous_output: StageOutput | None) -> bool:
        """Determine if this stage should run based on conditions.

        Args:
            previous_output: Output from the previous stage (None if first stage)

        Returns:
            True if the stage should run
        """
        # Check skip_on_failure
        if previous_output is not None and not previous_output.success:
            if not self.skip_on_failure:
                return True  # Will run and likely fail
            return False  # Skip on failure

        # Check custom condition
        if self.condition is not None:
            return self.condition(previous_output)

        return True

    def run(self, previous_output: StageOutput | None = None) -> StageOutput:
        """Execute this pipeline stage.

        Args:
            previous_output: Output from the previous stage (can be used for config updates)

        Returns:
            StageOutput with results from this stage
        """
        # Create and run the pipeline
        pipeline = self.pipeline_cls(config=self.config)
        result = pipeline.run()
        return StageOutput.from_result(result)


def create_stage(
    name: str,
    pipeline_cls: type[BasePipeline],
    config: BasePipelineSettings,
    *,
    skip_on_failure: bool = False,
    condition: Callable[[StageOutput | None], bool] | None = None,
) -> PipelineStage:
    """Factory function to create a pipeline stage.

    Args:
        name: Human-readable name for the stage
        pipeline_cls: Pipeline class to use
        config: Configuration for the pipeline
        skip_on_failure: Whether to skip if previous stage failed
        condition: Optional condition function

    Returns:
        Configured PipelineStage
    """
    return PipelineStage(
        name=name,
        pipeline_cls=pipeline_cls,
        config=config,
        skip_on_failure=skip_on_failure,
        condition=condition,
    )


# Common condition functions
def has_outputs(output: StageOutput | None) -> bool:
    """Condition: previous stage must have produced outputs."""
    if output is None:
        return True  # First stage always runs
    return len(output.outputs) > 0


def has_metadata_key(key: str) -> Callable[[StageOutput | None], bool]:
    """Create a condition that checks for a specific metadata key."""

    def check(output: StageOutput | None) -> bool:
        if output is None:
            return True
        return key in output.metadata

    return check


def is_successful(output: StageOutput | None) -> bool:
    """Condition: previous stage must have succeeded."""
    if output is None:
        return True
    return output.success
