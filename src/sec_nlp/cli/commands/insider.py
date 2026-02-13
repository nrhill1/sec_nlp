"""Insider pipeline CLI command."""

from pydantic import Field
from pydantic_settings import CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand
from sec_nlp.pipelines.presets.insider import InsiderPipeline, InsiderSettings


class Insider(InsiderSettings, BasePipelineCommand):
    """Analyze Form 3/4/5 insider transactions."""

    @classmethod
    def pipeline_class(cls) -> type[InsiderPipeline]:
        return InsiderPipeline

    symbols: CliPositionalArg[list[str]] = Field(
        default_factory=lambda: ["AAPL"],
        description="Ticker symbols to process (e.g., AAPL MSFT).",
    )

    def _get_header_subtitle(self) -> str:
        return "Insider Transactions"
