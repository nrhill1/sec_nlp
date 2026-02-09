# src/sec_nlp/pipelines/composition/chain.py
"""Pipeline chain for composing multiple pipelines."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.infra.logger import log_divider, logger
from sec_nlp.pipelines.base.config import BasePipelineSettings
from sec_nlp.pipelines.base.pipeline import BasePipeline
from sec_nlp.pipelines.base.result import BasePipelineResult
from sec_nlp.types import JsonObject, ResultDict

from .stage import PipelineStage, StageOutput, create_stage


class StageResult(BaseModel):
    """Result from running a single stage in the chain."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    stage_name: str = Field(
        description="Name of the stage",
    )
    output: StageOutput = Field(
        description="Output from the stage",
    )
    duration_seconds: float = Field(
        description="Time taken to run the stage in seconds",
    )
    skipped: bool = Field(
        default=False,
        description="Whether the stage was skipped",
    )


class ChainResult(BasePipelineResult):
    """Result from running a pipeline chain."""

    pipeline_type: ClassVar[Literal["chain"]] = "chain"

    model_config = ConfigDict(
        frozen=True,
        arbitrary_types_allowed=True,
    )

    stage_results: list[StageResult] = Field(
        default_factory=list,
        description="Results from each stage in the chain",
    )
    total_duration_seconds: float = Field(
        default=0.0,
        description="Total time taken to run the chain",
    )

    def summary_fields(self) -> JsonObject:
        """Return summary fields for display."""
        successful_stages = sum(
            1 for r in self.stage_results if r.output.success and not r.skipped
        )
        skipped_stages = sum(1 for r in self.stage_results if r.skipped)
        failed_stages = sum(
            1
            for r in self.stage_results
            if not r.output.success and not r.skipped
        )

        return {
            **self.base_summary_fields(),
            "stages_total": len(self.stage_results),
            "stages_successful": successful_stages,
            "stages_skipped": skipped_stages,
            "stages_failed": failed_stages,
            "duration_seconds": self.total_duration_seconds,
        }


class PipelineChain(BaseModel):
    """Chain multiple pipelines together for sequential execution.

    Example:
        chain = (
            PipelineChain(name="EFTS to Analysis")
            .add_stage("efts", EFTSPipeline, efts_config)
            .add_stage("analyze", AnalyzePipeline, analyze_config, condition=has_outputs)
        )
        result = chain.run()
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )

    name: str = Field(
        default="pipeline_chain",
        description="Name of the chain",
    )
    stages: list[PipelineStage] = Field(
        default_factory=list,
        description="Ordered list of pipeline stages",
    )
    stop_on_failure: bool = Field(
        default=True,
        description="Whether to stop the chain if a stage fails",
    )
    verbose: bool = Field(
        default=True,
        description="Enable verbose logging",
    )

    def add_stage(
        self,
        name: str,
        pipeline_cls: type[BasePipeline],
        config: BasePipelineSettings,
        *,
        skip_on_failure: bool = False,
        condition: Callable[[StageOutput | None], bool] | None = None,
    ) -> Self:
        """Add a pipeline stage to the chain.

        Args:
            name: Human-readable name for the stage
            pipeline_cls: Pipeline class to use
            config: Configuration for the pipeline
            skip_on_failure: Whether to skip this stage if previous failed
            condition: Optional condition function to determine if stage runs

        Returns:
            Self for method chaining
        """
        stage = create_stage(
            name=name,
            pipeline_cls=pipeline_cls,
            config=config,
            skip_on_failure=skip_on_failure,
            condition=condition,
        )
        self.stages.append(stage)
        return self

    def run(self) -> ChainResult:
        """Execute all stages in the chain sequentially.

        Returns:
            ChainResult with results from all stages
        """
        chain_start = perf_counter()
        stage_results: list[StageResult] = []
        all_outputs: list[Path] = []
        combined_metadata: ResultDict = {
            "chain_name": self.name,
            "stages": [],
        }

        if self.verbose:
            log_divider(logger, color="magenta")
            logger.info(
                "Starting pipeline chain: %s (%d stages)",
                self.name,
                len(self.stages),
            )

        previous_output: StageOutput | None = None
        chain_failed = False

        for i, stage in enumerate(self.stages, 1):
            stage_start = perf_counter()

            if self.verbose:
                log_divider(logger, color="cyan")
                logger.info(
                    "[%d/%d] Stage: %s (%s)",
                    i,
                    len(self.stages),
                    stage.name,
                    stage.pipeline_cls.__name__,
                )

            # Check if stage should run
            if not stage.should_run(previous_output):
                if self.verbose:
                    logger.info(
                        "Skipping stage %s (condition not met)", stage.name
                    )

                skipped_result = StageResult(
                    stage_name=stage.name,
                    output=StageOutput(
                        success=True,
                        error="Skipped due to condition",
                    ),
                    duration_seconds=perf_counter() - stage_start,
                    skipped=True,
                )
                stage_results.append(skipped_result)
                continue

            # Check if we should stop due to previous failure
            if chain_failed and self.stop_on_failure:
                if self.verbose:
                    logger.info(
                        "Skipping stage %s (chain stopped on failure)",
                        stage.name,
                    )

                skipped_result = StageResult(
                    stage_name=stage.name,
                    output=StageOutput(
                        success=False,
                        error="Skipped due to previous stage failure",
                    ),
                    duration_seconds=0.0,
                    skipped=True,
                )
                stage_results.append(skipped_result)
                continue

            # Run the stage
            try:
                output = stage.run(previous_output)
                duration = perf_counter() - stage_start

                if self.verbose:
                    status = "✓" if output.success else "✗"
                    logger.info(
                        "%s Stage %s completed in %.2fs (outputs=%d)",
                        status,
                        stage.name,
                        duration,
                        len(output.outputs),
                    )

                stage_result = StageResult(
                    stage_name=stage.name,
                    output=output,
                    duration_seconds=duration,
                    skipped=False,
                )
                stage_results.append(stage_result)

                # Accumulate outputs and metadata
                all_outputs.extend(output.outputs)
                stage_meta = {
                    "name": stage.name,
                    "success": output.success,
                    "outputs": len(output.outputs),
                    "duration": duration,
                }
                combined_metadata["stages"].append(stage_meta)

                # Track failure state
                if not output.success:
                    chain_failed = True

                previous_output = output

            except Exception as e:
                duration = perf_counter() - stage_start
                logger.exception("Stage %s failed with exception", stage.name)

                error_output = StageOutput(
                    success=False,
                    error=f"{type(e).__name__}: {e}",
                )
                stage_result = StageResult(
                    stage_name=stage.name,
                    output=error_output,
                    duration_seconds=duration,
                    skipped=False,
                )
                stage_results.append(stage_result)
                chain_failed = True
                previous_output = error_output

        total_duration = perf_counter() - chain_start
        chain_success = all(
            r.output.success or r.skipped for r in stage_results
        )

        if self.verbose:
            log_divider(logger, color="magenta")
            status = "✓ SUCCESS" if chain_success else "✗ FAILED"
            logger.info(
                "Chain %s completed: %s (%.2fs total)",
                self.name,
                status,
                total_duration,
            )

        combined_metadata["total_duration"] = total_duration
        combined_metadata["chain_success"] = chain_success

        return ChainResult(
            success=chain_success,
            outputs=all_outputs,
            metadata=combined_metadata,
            stage_results=stage_results,
            total_duration_seconds=total_duration,
            error=None if chain_success else "One or more stages failed",
        )

    def __len__(self) -> int:
        """Return number of stages in the chain."""
        return len(self.stages)

    def __repr__(self) -> str:
        stage_names = [s.name for s in self.stages]
        return f"PipelineChain(name={self.name!r}, stages={stage_names})"
