from pydantic_settings import CliPositionalArg as CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand as BasePipelineCommand
from sec_nlp.pipelines.presets.holdings import (
    HoldingsPipeline as HoldingsPipeline,
    HoldingsSettings as HoldingsSettings,
)

class Holdings(HoldingsSettings, BasePipelineCommand):
    @classmethod
    def pipeline_class(cls) -> type[HoldingsPipeline]: ...
    symbols: CliPositionalArg[list[str]]
