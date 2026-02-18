from pydantic_settings import CliPositionalArg as CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand as BasePipelineCommand
from sec_nlp.pipelines.presets.events import (
    EventsPipeline as EventsPipeline,
    EventsSettings as EventsSettings,
)

class Events(EventsSettings, BasePipelineCommand):
    @classmethod
    def pipeline_class(cls) -> type[EventsPipeline]: ...
    symbols: CliPositionalArg[list[str]]
