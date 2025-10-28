from pathlib import Path
from typing import Literal

from _typeshed import Incomplete

from sec_nlp.pipelines.base import BaseConfig as BaseConfig
from sec_nlp.pipelines.base import BasePipeline as BasePipeline
from sec_nlp.pipelines.base import BaseResult as BaseResult
from sec_nlp.pipelines.registry import PipelineRegistry as PipelineRegistry

class AnalysisConfig(BaseConfig):
    model_config: Incomplete
    pipeline_type: Literal["analysis"]
    input_path: Path
    output_path: Path | None
    analysis_type: Literal["sentiment", "trends", "comparison"]
    aggregate: bool
    @classmethod
    def validate_input_path(cls, v: Path) -> Path: ...
    def validate_config(self) -> None: ...

class AnalysisResult(BaseResult): ...

class AnalysisPipeline(BasePipeline[AnalysisConfig, AnalysisResult]):
    description: str
    requires_model: bool
    requires_vector_db: bool
    def validate_inputs(self) -> None: ...
    def run(self, **kwargs) -> BaseResult: ...
