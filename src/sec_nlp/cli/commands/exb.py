# src/sec_nlp/cli/commands/exb.py
"""Exhibit pipeline CLI command."""

from pydantic import Field
from pydantic_settings import CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand
from sec_nlp.core.infra.logger import bullet_line, logger
from sec_nlp.pipelines.presets.exb import (
    ExhibitConfig,
    ExhibitPipeline,
)


class Exb(ExhibitConfig, BasePipelineCommand):
    """Extract exhibit content by category.

    Examples:
        # Analyze exhibits for a company
        sec-nlp exb DE

        # Multiple companies
        sec-nlp exb DE CAT

        # Limit to specific exhibit categories
        sec-nlp exb DE --exhibit-categories subsidiaries consents

        # Or specify exhibit numbers directly
        sec-nlp exb DE --exhibit-numbers 21 23

        # With custom search terms (contract exhibits)
        sec-nlp exb DE --search-terms exclusive aftermarket
    """

    @classmethod
    def pipeline_class(cls) -> type[ExhibitPipeline]:
        return ExhibitPipeline

    symbols: CliPositionalArg[list[str]] = Field(
        default_factory=lambda: ["CAT", "DE", "GE", "CMI", "PCAR"],
        description="Ticker symbols to process (e.g., DE CAT).",
    )

    def _get_header_subtitle(self) -> str:
        return "Exhibits"

    def _log_config_details(self) -> None:
        """Log exhibit-specific configuration."""
        super()._log_config_details()
        categories = [
            str(category)
            for category in self.get_exhibit_categories()
            if category
        ]
        if categories:
            categories_display = ", ".join(categories[:6])
            if len(categories) > 6:
                categories_display += "..."
            logger.info(
                bullet_line(
                    "Exhibit categories",
                    categories_display,
                    color="green",
                )
            )
        terms_display = ", ".join(self.search_terms[:6])
        if len(self.search_terms) > 6:
            terms_display += "..."
        logger.info(bullet_line("Search terms", terms_display, color="green"))
