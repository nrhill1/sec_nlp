"""Financials pipeline CLI command."""

from pydantic import Field
from pydantic_settings import CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand
from sec_nlp.pipelines.presets.financials import (
    FinancialsPipeline,
    FinancialsSettings,
)


class Financials(FinancialsSettings, BasePipelineCommand):
    """Extract structured financial statements from filing XBRL."""

    @classmethod
    def pipeline_class(cls) -> type[FinancialsPipeline]:
        return FinancialsPipeline

    symbols: CliPositionalArg[list[str]] = Field(
        default_factory=lambda: ["AAPL"],
        description="Ticker symbols to process (e.g., AAPL MSFT).",
    )

    def _get_header_subtitle(self) -> str:
        return "Financial Statements"
