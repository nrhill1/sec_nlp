from pydantic_settings import CliPositionalArg as CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand as BasePipelineCommand
from sec_nlp.pipelines.presets.retrieve import (
    RetrievePipeline as RetrievePipeline,
    RetrieveSettings as RetrieveSettings,
)

class Retrieve(RetrieveSettings, BasePipelineCommand):
    @classmethod
    def pipeline_class(cls) -> type[RetrievePipeline]: ...
    symbols: CliPositionalArg[list[str]]
