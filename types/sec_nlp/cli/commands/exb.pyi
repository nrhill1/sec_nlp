from pydantic_settings import CliPositionalArg as CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand as BasePipelineCommand
from sec_nlp.core.infra.logger import (
    bullet_line as bullet_line,
    logger as logger,
)
from sec_nlp.pipelines.presets.exb import (
    ExhibitConfig as ExhibitConfig,
    ExhibitPipeline as ExhibitPipeline,
)

class Exb(ExhibitConfig, BasePipelineCommand):
    @classmethod
    def pipeline_class(cls) -> type[ExhibitPipeline]: ...
    symbols: CliPositionalArg[list[str]]
