from pydantic_settings import CliPositionalArg as CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand as BasePipelineCommand
from sec_nlp.core.infra.logger import (
    bullet_line as bullet_line,
    color_text as color_text,
    logger as logger,
)
from sec_nlp.pipelines.base.result import (
    BasePipelineResult as BasePipelineResult,
)
from sec_nlp.pipelines.presets.analyze import (
    AnalyzeConfig as AnalyzeConfig,
    AnalyzePipeline as AnalyzePipeline,
    AnalyzeResult as AnalyzeResult,
)

class AnalyzeCommand(AnalyzeConfig, BasePipelineCommand):
    @classmethod
    def pipeline_class(cls) -> type[AnalyzePipeline]: ...
    symbols: CliPositionalArg[list[str]]
