"""Holdings pipeline CLI command."""

from pydantic import Field
from pydantic_settings import CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand
from sec_nlp.pipelines.presets.holdings import (
    HoldingsPipeline,
    HoldingsSettings,
)


class Holdings(HoldingsSettings, BasePipelineCommand):
    """Analyze institutional 13F holdings and quarter-over-quarter changes."""

    @classmethod
    def pipeline_class(cls) -> type[HoldingsPipeline]:
        return HoldingsPipeline

    symbols: CliPositionalArg[list[str]] = Field(
        default_factory=lambda: ["AAPL"],
        description="Ticker symbols to process (e.g., AAPL MSFT).",
    )

    def _get_header_subtitle(self) -> str:
        return "Institutional Holdings"
