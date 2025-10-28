# sec_nlp/cli/commands/info.py
"""Info command to show pipeline registry information."""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from sec_nlp.pipelines.registry import PipelineRegistry, RegistryState

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
    if json_output:
        state = RegistryState.from_registry()
        console.print(state.to_json())
        return

    if pipeline_type:
        # Show specific pipeline info
        try:
            info = PipelineRegistry.get_info(pipeline_type)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=1) from e

        # Create info table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")

        table.add_row("Type", info.type)
        table.add_row("Class", info.class_name)
        table.add_row("Description", info.description)
        table.add_row("Module", info.module)
        table.add_row("Config Class", info.config_class_name)
        table.add_row(
            "Requires Model",
            "✓" if info.requires_model else "✗",
        )
        table.add_row(
            "Requires Vector DB",
            "✓" if info.requires_vector_db else "✗",
        )

        console.print(
            Panel(
                table,
                title=f"[bold cyan]Pipeline: {pipeline_type}[/bold cyan]",
                border_style="cyan",
            )
        )

        # Show requirements check
        checks = PipelineRegistry.validate_requirements(pipeline_type)
        console.print("\n[bold]Requirements Check:[/bold]")
        for check, status in checks.items():
            icon = "[green]✓[/green]" if status else "[red]✗[/red]"
            check_name = check.replace("_", " ").title()
            console.print(f"  {icon} {check_name}")

    else:
        # Show all pipelines
        pipelines = PipelineRegistry.get_all_info()

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

        for info in pipelines.values():
            table.add_row(
                info.type,
                info.description,
                "✓" if info.requires_model else "✗",
                "✓" if info.requires_vector_db else "✗",
                info.config_class_name,
            )

        console.print(table)
        console.print(f"\n[dim]Total: {len(pipelines)} pipeline(s) registered[/dim]")
        console.print("\n[cyan]Tip:[/cyan] Use [green]sec-nlp info <type>[/green] for details")
