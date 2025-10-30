# src/sec_nlp/cli/__main__.py
"""Main CLI application."""

from __future__ import annotations

import typer
from rich.console import Console

from sec_nlp.cli.commands import (
    analyze_command,
    embed_command,
    info_command,
    summarize_command,
    version_command,
)

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
        raise typer.Exit()


@main.callback()
def main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """
    [bold cyan]SEC NLP Pipeline[/bold cyan]

    A powerful CLI tool for downloading, parsing, and summarizing SEC filings
    using local LLMs and vector embeddings.

    [yellow]Quick Start:[/yellow]
      [green]$ sec-nlp run AAPL[/green]                    # Analyze Apple's filings
      [green]$ sec-nlp run -i[/green]                      # Interactive mode
      [green]$ sec-nlp run AAPL MSFT --help[/green]        # See all options

    [yellow]Available Commands:[/yellow]
      [cyan]run[/cyan]      - Download and analyze SEC filings
      [cyan]analyze[/cyan]  - Analyze existing summaries (coming soon)
      [cyan]embed[/cyan]    - Embed documents into vector store (coming soon)
      [cyan]version[/cyan]  - Show version information

    [yellow]Documentation:[/yellow]
      https://github.com/nrhill1/sec_nlp
    """
    pass


main.command(
    name="summarize",
    help="[green]Run SEC filing summary pipeline[/green]",
    rich_help_panel="Main Commands",
)(summarize_command)

main.command(
    name="analyze",
    help="[yellow]Analyze existing summaries[/yellow] [dim](coming soon)[/dim]",
    rich_help_panel="Analysis Commands",
)(analyze_command)

main.command(
    name="embed",
    help="[yellow]Embed documents into vector store[/yellow] [dim](coming soon)[/dim]",
    rich_help_panel="Analysis Commands",
)(embed_command)

main.command(
    name="version",
    help="Show version information",
    rich_help_panel="Utility Commands",
)(version_command)

main.command(
    name="info",
    help="Show pipeline information and registry",
    rich_help_panel="Utility Commands",
)(info_command)

if __name__ == "__main__":
    main()
