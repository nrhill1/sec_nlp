from pydantic_settings import CliPositionalArg as CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand as BasePipelineCommand
from sec_nlp.pipelines.presets.news import (
    NewsPipeline as NewsPipeline,
    NewsSettings as NewsSettings,
)

class News(NewsSettings, BasePipelineCommand):
    @classmethod
    def pipeline_class(cls) -> type[NewsPipeline]: ...
    symbols: CliPositionalArg[list[str]]
