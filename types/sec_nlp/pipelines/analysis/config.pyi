from pathlib import Path
from typing import Literal

from _typeshed import Incomplete

from sec_nlp.pipelines.base import BaseConfig as BaseConfig

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
