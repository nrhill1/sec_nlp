# src/sec_nlp/cli/__main__.py
"""Main CLI application."""

from __future__ import annotations

import typer
from rich.console import Console

from sec_nlp.cli.commands import (
    info_command,
    version_command,
)
from sec_nlp.pipelines.registry import PipelineRegistry

console = Console()

main = typer.Typer(
    name="sec-nlp",
    help="SEC NLP Pipeline - Download, parse, and summarize SEC filings using LLMs",
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    rich_markup_mode="rich",
)


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        version_command()


if __name__ == "__main__":
    main()


# main.command(
#     name="analyze",
#     help="[yellow]Analyze existing summaries[/yellow] [dim](coming soon)[/dim]",
#     rich_help_panel="Analysis Commands",
# )(analyze_command)

# main.command(
#     name="embed",
#     help="[yellow]Embed documents into vector store[/yellow] [dim](coming soon)[/dim]",
#     rich_help_panel="Analysis Commands",
# )(embed_command)
