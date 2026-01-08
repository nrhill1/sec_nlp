from pydantic_settings import CliPositionalArg as CliPositionalArg

from sec_nlp.cli.command import PipelineCommand as PipelineCommand
from sec_nlp.core.infra.logger import (
    bullet_line as bullet_line,
    color_text as color_text,
    logger as logger,
)
from sec_nlp.pipelines.base.result import BaseResult as BaseResult
from sec_nlp.pipelines.presets.analyze import (
    AnalyzeConfig as AnalyzeConfig,
    AnalyzePipeline as AnalyzePipeline,
    AnalyzeResult as AnalyzeResult,
)

class AnalyzeCommand(AnalyzeConfig, PipelineCommand):
    @classmethod
    def pipeline_class(cls) -> type[AnalyzePipeline]: ...
    symbols: CliPositionalArg[list[str]]
