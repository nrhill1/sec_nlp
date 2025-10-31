# sec_nlp/pipelines/analysis.py (future)
"""Analysis pipeline for existing summaries."""

from typing import ClassVar

from pydantic import BaseModel

from sec_nlp.pipelines.base import BasePipeline, BaseResult

from .config import AnalysisConfig


class AnalysisInput(BaseModel):
    pipeline_type: ClassVar[str] = "analysis"


class AnalysisResult(BaseResult): ...


# TODO: Finish the analysis pipeline
class AnalysisPipeline(BasePipeline[AnalysisConfig, AnalysisResult]):
    """Pipeline for analyzing existing summaries."""

    description = "Analyze existing SEC filing summaries"
    requires_llm = False
    requires_vector_db = False

    def validate_inputs(self, input: AnalysisInput) -> None:
        """Validate inputs."""
        if not self.config.input_path.exists():
            raise ValueError(f"Input path not found: {self.config.input_path}")

    def run(self, input_data: AnalysisInput | None = None) -> AnalysisResult:
        """Run analysis pipeline."""
        # TODO: Implement
        return AnalysisResult(
            success=True,
            metadata={"status": "not_implemented"},
        )
