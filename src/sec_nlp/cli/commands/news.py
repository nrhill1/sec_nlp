# src/sec_nlp/cli/commands/news.py
"""News pipeline CLI command."""

from pydantic import Field
from pydantic_settings import CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand
from sec_nlp.pipelines.presets.news import NewsPipeline, NewsSettings


class News(NewsSettings, BasePipelineCommand):
    """Monitor financial news and correlate headline activity with filings."""

    @classmethod
    def pipeline_class(cls) -> type[NewsPipeline]:
        return NewsPipeline

    symbols: CliPositionalArg[list[str]] = Field(
        default_factory=lambda: ["AAPL"],
        description="Ticker symbols to process (e.g., AAPL MSFT).",
    )

    def _get_header_subtitle(self) -> str:
        """Build subtitle text for the news command header."""
        return "News Monitoring"
