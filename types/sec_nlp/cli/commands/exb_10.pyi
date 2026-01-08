from pydantic_settings import CliPositionalArg as CliPositionalArg

from sec_nlp.cli.command import PipelineCommand as PipelineCommand
from sec_nlp.core.infra.logger import (
    bullet_line as bullet_line,
    logger as logger,
)
from sec_nlp.pipelines.presets.exb_10 import (
    Exhibit10Config as Exhibit10Config,
    Exhibit10Pipeline as Exhibit10Pipeline,
)

class Exb10(Exhibit10Config, PipelineCommand):
    @classmethod
    def pipeline_class(cls) -> type[Exhibit10Pipeline]: ...
    symbols: CliPositionalArg[list[str]]
