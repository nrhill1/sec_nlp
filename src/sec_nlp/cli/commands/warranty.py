# src/sec_nlp/cli/commands/warranty.py
"""Warranty pipeline CLI command."""

from pydantic import Field
from pydantic_settings import CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand
from sec_nlp.pipelines.presets.warranty import (
    WarrantyConfig,
    WarrantyPipeline,
)


class Warranty(WarrantyConfig, BasePipelineCommand):
    """Extract warranty-related data from SEC filings."""

    @classmethod
    def pipeline_class(cls) -> type[WarrantyPipeline]:
        return WarrantyPipeline

    symbols: CliPositionalArg[list[str]] = Field(
        default_factory=lambda: ["CAT", "DE", "PCAR"],
        description="Ticker symbols to process (e.g., AAPL MSFT).",
    )

    def _get_header_subtitle(self) -> str:
        return "Warranty Signals"
