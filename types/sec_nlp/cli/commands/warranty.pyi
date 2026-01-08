from pydantic_settings import CliPositionalArg as CliPositionalArg

from sec_nlp.cli.command import PipelineCommand as PipelineCommand
from sec_nlp.pipelines.presets.warranty import (
    WarrantyConfig as WarrantyConfig,
    WarrantyPipeline as WarrantyPipeline,
)

class Warranty(WarrantyConfig, PipelineCommand):
    @classmethod
    def pipeline_class(cls) -> type[WarrantyPipeline]: ...
    symbols: CliPositionalArg[list[str]]
