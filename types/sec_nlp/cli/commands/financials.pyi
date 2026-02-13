from pydantic_settings import CliPositionalArg as CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand as BasePipelineCommand
from sec_nlp.pipelines.presets.financials import (
    FinancialsPipeline as FinancialsPipeline,
    FinancialsSettings as FinancialsSettings,
)

class Financials(FinancialsSettings, BasePipelineCommand):
    @classmethod
    def pipeline_class(cls) -> type[FinancialsPipeline]: ...
    symbols: CliPositionalArg[list[str]]
