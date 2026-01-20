from pydantic_settings import CliPositionalArg as CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand as BasePipelineCommand
from sec_nlp.pipelines.presets.warranty import (
    WarrantyConfig as WarrantyConfig,
    WarrantyPipeline as WarrantyPipeline,
)

class Warranty(WarrantyConfig, BasePipelineCommand):
    @classmethod
    def pipeline_class(cls) -> type[WarrantyPipeline]: ...
    symbols: CliPositionalArg[list[str]]
