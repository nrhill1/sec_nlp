# src/sec_nlp/cli/commands/root.py
# src/sec_nlp/cli/commands/run.py
"""Run pipeline commands"""

from datetime import datetime

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    CliApp,
    CliSubCommand,
    SettingsConfigDict,
)

from sec_nlp.core.infra.logger import logger

from .analyze import AnalyzeCommand
from .chat import Chat
from .clean import Clean
from .efts import EFTS
from .events import Events
from .exb import Exb
from .financials import Financials
from .flow import Flow
from .holdings import Holdings
from .insider import Insider
from .market import Market
from .news import News
from .qdrant import Qdrant
from .retrieve import Retrieve
from .runs import Runs
from .version import Version
from .warranty import Warranty


class Root(BaseSettings):
    """SEC NLP - Analyze SEC filings with local LLMs."""

    model_config = SettingsConfigDict(
        defer_build=True,
        cli_prog_name="sec-nlp",
        cli_enforce_required=True,
        cli_exit_on_error=True,
        cli_implicit_flags=True,
        cli_kebab_case=True,
        nested_model_default_partial_update=True,
        case_sensitive=False,
    )

    analyze: CliSubCommand[AnalyzeCommand] = Field(
        description="Analyze SEC filings with configurable filtering and LLM"
    )

    chat: CliSubCommand[Chat] = Field(
        description="Run retrieval-augmented chat over indexed filings"
    )

    flow: CliSubCommand[Flow] = Field(
        description="Run multi-stage flow specs (retrieve -> chat, etc.)"
    )

    warranty: CliSubCommand[Warranty] = Field(
        description="Run the warranty pipeline"
    )

    exb: CliSubCommand[Exb] = Field(description="Run the exhibit pipeline")

    financials: CliSubCommand[Financials] = Field(
        description="Run the financial statement extraction pipeline"
    )

    holdings: CliSubCommand[Holdings] = Field(
        description="Run the institutional holdings analysis pipeline"
    )

    insider: CliSubCommand[Insider] = Field(
        description="Run the insider trading analysis pipeline"
    )

    news: CliSubCommand[News] = Field(
        description="Run the news monitoring and correlation pipeline"
    )

    retrieve: CliSubCommand[Retrieve] = Field(
        description="Run the EFTS-first retrieval pipeline"
    )

    events: CliSubCommand[Events] = Field(
        description="Run the event detection and timeline pipeline"
    )

    efts: CliSubCommand[EFTS] = Field(
        description="Search SEC EDGAR filings using Full-Text Search API"
    )

    clean: CliSubCommand[Clean] = Field(
        description="Clear downloads, outputs, or logs"
    )

    qdrant: CliSubCommand[Qdrant] = Field(
        description="Manage Qdrant collections (list, info, create, delete, search)"
    )

    market: CliSubCommand[Market] = Field(
        description="Retrieve Yahoo Finance market data (latest or range)."
    )

    runs: CliSubCommand[Runs] = Field(
        description="Manage pipeline runs (list, info, delete, prune, stats)"
    )

    version: CliSubCommand[Version] = Field(
        description="Display current version"
    )

    def cli_cmd(self) -> None:
        """Execute the selected subcommand."""

        # Skip timing if running Version
        if self.version:
            CliApp.run_subcommand(self)
            return

        logger.debug(" Starting execution...")

        start = datetime.now()
        CliApp.run_subcommand(self)
        elapsed = datetime.now() - start

        days = elapsed.days
        hours, remainder = divmod(elapsed.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        formatted_delta = (
            f"{days} days: {hours:02d}h {minutes:02d}m {seconds:02d}s"
        )

        logger.info("Finished in %s", formatted_delta)
