# src/sec_nlp/cli/commands/info.py
"""Info command to show pipeline registry information."""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from sec_nlp.pipelines.registry import PipelineRegistry

console = Console()


def info_command(
    pipeline_type: str | None = typer.Argument(
        None,
        help="Pipeline type to show info for (omit to show all)",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON",
    ),
) -> None:
    """
    Show information about available pipeline types.

    \b
    Examples:
      # Show all registered pipelines
      $ sec-nlp info

      \b
      # Show specific pipeline details
      $ sec-nlp info summary

      \b
      # Output as JSON
      $ sec-nlp info --json
    """
    # TODO: Handle JSON output

    if pipeline_type:
        try:
            pipeline = PipelineRegistry.get_pipeline(pipeline_type)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=1) from e

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")

        table.add_row("Type", pipeline.pipeline_type)
        table.add_row("Class", pipeline.__name__)
        table.add_row("Description", pipeline.description)
        table.add_row("Module", pipeline.__module__)
        table.add_row("Config Class", pipeline._config_class.__name__)
        table.add_row(
            "Requires LLM",
            "✓" if pipeline.requires_llm else "✗",
        )
        table.add_row(
            "Requires Vector DB",
            "✓" if pipeline.requires_vector_db else "✗",
        )

        console.print(
            Panel(
                table,
                title=f"[bold cyan]Pipeline: {pipeline_type}[/bold cyan]",
                border_style="cyan",
            )
        )

    else:
        pipelines = PipelineRegistry.get_all_pipelines()

        if not pipelines:
            console.print("[yellow]No pipelines registered[/yellow]")
            return

        table = Table(
            title="[bold cyan]Registered Pipelines[/bold cyan]",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Type", style="yellow", no_wrap=True)
        table.add_column("Description", style="white")
        table.add_column("Model", justify="center", width=6)
        table.add_column("Vector DB", justify="center", width=9)
        table.add_column("Config", style="dim")

        for pipeline in pipelines:
            table.add_row(
                pipeline.pipeline_type,
                pipeline.description,
                "✓" if pipeline.requires_llm else "✗",
                "✓" if pipeline.requires_vector_db else "✗",
                f"{pipeline._config_class.__module__}.{pipeline._config_class.__name__} ",
            )

        console.print(table)
        console.print(
            f"\n[dim]Total: {len(pipelines)} pipeline(s) registered[/dim]"
        )
        console.print(
            "\n[cyan]Tip:[/cyan] Use [green]sec-nlp info <type>[/green] for details"
        )
