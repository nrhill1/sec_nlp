# sec_nlp/pipelines/analysis.py (future)
"""Analysis pipeline for existing summaries."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SettingsConfigDict, field_validator

from sec_nlp.pipelines.base import BaseConfig, BasePipeline, BaseResult
from sec_nlp.pipelines.registry import PipelineRegistry


class AnalysisConfig(BaseConfig):
    """Configuration for summary analysis pipeline."""

    model_config = SettingsConfigDict(
        env_prefix="ANALYSIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    pipeline_type: Literal["analysis"] = "analysis"

    # Input options
    input_path: Path = Field(
        ...,
        description="Path to summaries directory or JSON file",
    )
    output_path: Path | None = Field(
        default=None,
        description="Output path for analysis results",
    )

    # Analysis options
    analysis_type: Literal["sentiment", "trends", "comparison"] = Field(
        default="sentiment",
        description="Type of analysis to perform",
    )
    aggregate: bool = Field(
        default=True,
        description="Aggregate results across all filings",
    )

    @field_validator("input_path")
    @classmethod
    def validate_input_path(cls, v: Path) -> Path:
        """Validate input path exists."""
        if not v.exists():
            raise ValueError(f"Input path not found: {v}")
        return v

    def validate_config(self) -> None:
        """Validate pipeline-specific configuration."""
        if not self.input_path.is_dir() and self.input_path.suffix not in (
            ".json",
            ".yaml",
            ".yml",
        ):
            raise ValueError("input_path must be a directory or JSON file")


class AnalysisResult(BaseResult): ...


@PipelineRegistry.register("analysis")
class AnalysisPipeline(BasePipeline[AnalysisConfig, AnalysisResult]):
    """Pipeline for analyzing existing summaries."""

    description = "Analyze existing SEC filing summaries"
    requires_model = False
    requires_vector_db = False

    def validate_inputs(self) -> None:
        """Validate inputs."""
        if not self.config.input_path.exists():
            raise ValueError(f"Input path not found: {self.config.input_path}")

    def run(self, **kwargs) -> BaseResult:
        """Run analysis pipeline."""
        # TODO: Implement
        return BaseResult(
            success=True,
            pipeline_type=self.pipeline_type,
            metadata={"status": "not_implemented"},
        )
