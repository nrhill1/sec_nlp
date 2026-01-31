"""CLI commands for running analyze pipeline runnables in isolation."""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import CliPositionalArg

from .analyze import AnalyzeCommand


class AnalyzeSearchCommand(AnalyzeCommand):
    """Run the analyze pipeline with only the search runnable enabled."""

    symbols: CliPositionalArg[list[str]] = Field(
        default_factory=list,
        description="Ticker symbols to run vector search for (e.g., AAPL MSFT).",
    )
    runnables: list[
        Literal[
            "efts",
            "search",
            "analysis",
            "export",
            "market_correlation",
        ]
    ] = Field(
        default_factory=lambda: ["search", "export"],
        description="Runnables to execute (fixed for this command).",
    )


class AnalyzeAnalysisCommand(AnalyzeCommand):
    """Run the analyze pipeline with search + analysis enabled."""

    symbols: CliPositionalArg[list[str]] = Field(
        default_factory=list,
        description="Ticker symbols to analyze (e.g., AAPL MSFT).",
    )
    runnables: list[
        Literal[
            "efts",
            "search",
            "analysis",
            "export",
            "market_correlation",
        ]
    ] = Field(
        default_factory=lambda: ["search", "analysis", "export"],
        description="Runnables to execute (fixed for this command).",
    )


class AnalyzeMarketCorrelationCommand(AnalyzeCommand):
    """Run the analyze pipeline with market correlation enabled."""

    symbols: CliPositionalArg[list[str]] = Field(
        default_factory=list,
        description="Ticker symbols to analyze with market correlation.",
    )
    prompt: Literal["default", "market_correlation"] | None = Field(
        default="market_correlation",
        description="Prompt profile for analysis output.",
    )
    runnables: list[
        Literal[
            "efts",
            "search",
            "analysis",
            "export",
            "market_correlation",
        ]
    ] = Field(
        default_factory=lambda: [
            "search",
            "analysis",
            "export",
            "market_correlation",
        ],
        description="Runnables to execute (fixed for this command).",
    )
