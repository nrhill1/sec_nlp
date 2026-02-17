"""Retrieve pipeline CLI command."""

from pydantic import Field
from pydantic_settings import CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand
from sec_nlp.pipelines.presets.retrieve import (
    RetrievePipeline,
    RetrieveSettings,
)


class Retrieve(RetrieveSettings, BasePipelineCommand):
    """Retrieve ranked filing hits from EFTS candidate search."""

    @classmethod
    def pipeline_class(cls) -> type[RetrievePipeline]:
        return RetrievePipeline

    symbols: CliPositionalArg[list[str]] = Field(
        default_factory=lambda: ["AAPL"],
        description="Ticker symbols to process (e.g., AAPL MSFT).",
    )

    def _get_header_subtitle(self) -> str:
        return "Retrieval"
