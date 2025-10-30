from typing import ClassVar

from pydantic import BaseModel

from sec_nlp.pipelines.base import BasePipeline as BasePipeline
from sec_nlp.pipelines.base import BaseResult as BaseResult
from sec_nlp.pipelines.registry import PipelineRegistry as PipelineRegistry

from .config import AnalysisConfig as AnalysisConfig

class AnalysisInput(BaseModel):
    pipeline_type: ClassVar[str]

class AnalysisResult(BaseResult): ...

class AnalysisPipeline(
    BasePipeline[AnalysisConfig, AnalysisInput, AnalysisResult]
):
    description: str
    requires_llm: bool
    requires_vector_db: bool
    def validate_inputs(self, input: AnalysisInput) -> None: ...
    def run(
        self, input_data: AnalysisInput | None = None
    ) -> AnalysisResult: ...
