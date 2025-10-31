# src/sec_nlp/cli/__main__.py
"""Main CLI application."""

from __future__ import annotations

from sec_nlp.cli.commands import (
    version_command,
)


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        version_command()


def main(): ...


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
