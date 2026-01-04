# src/sec_nlp/cli/commands/exb_10.py
"""Exhibit 10 pipeline CLI command."""

from pydantic import Field
from pydantic_settings import CliPositionalArg

from sec_nlp.cli.command import PipelineCommand
from sec_nlp.core.infra.logger import bullet_line, logger
from sec_nlp.pipelines.presets.exb_10 import (
    Exhibit10Config,
    Exhibit10Pipeline,
)


class Exb10(Exhibit10Config, PipelineCommand):
    """Extract supplier contract information from Exhibit 10 of 10-K documents.

    Examples:
        # Analyze Exhibit 10 contracts for a company
        sec-nlp exb-10 DE

        # Multiple companies
        sec-nlp exb-10 DE CAT

        # With custom search terms
        sec-nlp exb-10 DE --search-terms exclusive aftermarket
    """

    @classmethod
    def pipeline_class(cls) -> type[Exhibit10Pipeline]:
        return Exhibit10Pipeline

    symbols: CliPositionalArg[list[str]] = Field(
        default_factory=lambda: ["CAT", "DE", "GE", "CMI", "PCAR"],
        description="Ticker symbols to process (e.g., DE CAT).",
    )

    def _get_header_subtitle(self) -> str:
        return "Material Contracts"

    def _log_config_details(self) -> None:
        """Log exhibit-10 specific configuration."""
        super()._log_config_details()
        terms_display = ", ".join(self.search_terms[:6])
        if len(self.search_terms) > 6:
            terms_display += "…"
        logger.info(bullet_line("Search terms", terms_display, color="green"))
