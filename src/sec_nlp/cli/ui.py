# src/sec_nlp/cli/ui.py
"""CLI UI utilities for rich formatting and user interaction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.tree import Tree

console = Console()


class CLIFormatter:
    """Rich formatting utilities for CLI output."""

    @staticmethod
    def print_header(title: str, subtitle: str | None = None) -> None:
        """Print a formatted header."""
        text = f"[bold cyan]{title}[/bold cyan]"
        if subtitle:
            text += f"\n[dim]{subtitle}[/dim]"
        console.print(Panel(text, border_style="cyan"))

    @staticmethod
    def print_success(message: str) -> None:
        """Print a success message."""
        console.print(f"[green]✓[/green] {message}")

    @staticmethod
    def print_error(message: str) -> None:
        """Print an error message."""
        console.print(f"[red]✗[/red] {message}", style="red")

    @staticmethod
    def print_warning(message: str) -> None:
        """Print a warning message."""
        console.print(f"[yellow]⚠[/yellow] {message}", style="yellow")

    @staticmethod
    def print_info(message: str) -> None:
        """Print an info message."""
        console.print(f"[blue]ℹ[/blue] {message}", style="blue")

    @staticmethod
    def print_config(
        config: dict[str, Any], title: str = "Configuration"
    ) -> None:
        """Print configuration in a formatted table."""
        table = Table(title=title, show_header=True, header_style="bold cyan")
        table.add_column("Setting", style="cyan", no_wrap=True)
        table.add_column("Value", style="green")

        for key, value in config.items():
            formatted_key = key.replace("_", " ").title()

            if isinstance(value, bool):
                formatted_value = "✓" if value else "✗"
                style = "green" if value else "red"
                table.add_row(formatted_key, formatted_value, style=style)
            elif isinstance(value, list):
                formatted_value = ", ".join(str(v) for v in value)
                table.add_row(formatted_key, formatted_value)
            elif isinstance(value, Path):
                table.add_row(formatted_key, str(value), style="blue")
            else:
                table.add_row(formatted_key, str(value))

        console.print(table)

    @staticmethod
    def print_results(results: dict[str, list[Path]], elapsed: float) -> None:
        """Print pipeline results in a formatted table."""
        table = Table(
            title=f"Pipeline Results ([cyan]{elapsed:.2f}s[/cyan])",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Symbol", style="yellow", no_wrap=True, width=10)
        table.add_column("Files", justify="right", style="green", width=8)
        table.add_column("Status", justify="center", width=8)
        table.add_column("Output Files", style="dim blue")

        for symbol, paths in results.items():
            count = len(paths)
            status = "[green]✓[/green]" if count > 0 else "[red]✗[/red]"
            files_list = "\n".join(p.name for p in paths[:3])
            if len(paths) > 3:
                files_list += f"\n... and {len(paths) - 3} more"

            table.add_row(
                symbol,
                str(count),
                status,
                files_list if count > 0 else "[dim]No results[/dim]",
            )

        console.print()
        console.print(table)

    @staticmethod
    def print_file_tree(root: Path, title: str = "Files") -> None:
        """Print a file tree."""
        tree = Tree(f"[bold cyan]{title}[/bold cyan]: {root}")

        def add_items(tree_node: Tree, path: Path) -> None:
            """Recursively add items to tree."""
            try:
                items = sorted(
                    path.iterdir(), key=lambda x: (not x.is_dir(), x.name)
                )
                for item in items[:10]:
                    if item.is_dir():
                        branch = tree_node.add(f"📁 [bold]{item.name}[/bold]")
                        add_items(branch, item)
                    else:
                        size = item.stat().st_size
                        size_str = format_size(size)
                        tree_node.add(f"📄 {item.name} [dim]({size_str})[/dim]")
            except PermissionError:
                tree_node.add("[red]Permission denied[/red]")

        add_items(tree, root)
        console.print(tree)

    @staticmethod
    def create_progress() -> Progress:
        """Create a rich progress bar."""
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        )


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    float_bytes = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if float_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        float_bytes /= 1024.0
    return f"{float_bytes:.1f}TB"


class InteractivePrompts:
    """Interactive prompts for user input."""

    @staticmethod
    def confirm(message: str, default: bool = False) -> Any:
        """Ask for confirmation."""
        return questionary.confirm(message, default=default).ask()

    @staticmethod
    def select(message: str, choices: list[str]) -> Any:
        """Select from a list of choices."""
        return questionary.select(message, choices=choices).ask()

    @staticmethod
    def text(message: str, default: str = "") -> Any:
        """Ask for text input."""
        return questionary.text(message, default=default).ask()

    @staticmethod
    def path(
        message: str, default: str = "", only_directories: bool = False
    ) -> Any:
        """Ask for a file path."""
        return questionary.path(
            message,
            default=default,
            only_directories=only_directories,
        ).ask()

    @staticmethod
    def select_symbols() -> list[str]:
        """Interactive symbol selection."""
        symbols_text = questionary.text(
            "Enter ticker symbols (space-separated):",
            default="AAPL",
        ).ask()
        return [s.strip().upper() for s in symbols_text.split()]

    @staticmethod
    def select_date_range() -> tuple[str, str]:
        """Interactive date range selection."""
        from datetime import date, timedelta

        today = date.today()
        one_year_ago = today - timedelta(days=365)

        console.print("\n[cyan]Date Range Selection[/cyan]")
        use_default = questionary.confirm(
            f"Use default range? ({one_year_ago} to {today})",
            default=True,
        ).ask()

        if use_default:
            return one_year_ago.isoformat(), today.isoformat()

        start = questionary.text(
            "Start date (YYYY-MM-DD):",
            default=one_year_ago.isoformat(),
        ).ask()

        end = questionary.text(
            "End date (YYYY-MM-DD):",
            default=today.isoformat(),
        ).ask()

        return start, end
