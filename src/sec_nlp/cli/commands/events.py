# src/sec_nlp/cli/commands/events.py
"""Events pipeline CLI command."""

from pydantic import Field
from pydantic_settings import CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand
from sec_nlp.pipelines.presets.events import EventsPipeline, EventsSettings


class Events(EventsSettings, BasePipelineCommand):
    """Detect material events from 8-K/6-K filings and score market impact."""

    @classmethod
    def pipeline_class(cls) -> type[EventsPipeline]:
        return EventsPipeline

    symbols: CliPositionalArg[list[str]] = Field(
        default_factory=lambda: ["AAPL"],
        description="Ticker symbols to process (e.g., AAPL MSFT).",
    )

    def _get_header_subtitle(self) -> str:
        return "Event Timeline"
