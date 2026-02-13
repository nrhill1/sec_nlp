from pydantic_settings import CliPositionalArg as CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand as BasePipelineCommand
from sec_nlp.pipelines.presets.insider import (
    InsiderPipeline as InsiderPipeline,
    InsiderSettings as InsiderSettings,
)

class Insider(InsiderSettings, BasePipelineCommand):
    @classmethod
    def pipeline_class(cls) -> type[InsiderPipeline]: ...
    symbols: CliPositionalArg[list[str]]
