# src/sec_nlp/cli/commands/summarize.py
"""Run command - dispatches to summary pipeline."""

from __future__ import annotations

from importlib.resources import as_file, files
from pathlib import Path

import typer
from dotenv import load_dotenv

from sec_nlp.core import FilingMode


def summarize_command(
    symbols: list[str] = typer.Argument(
        None,
        help="Stock ticker symbols",
    ),
    mode: FilingMode = typer.Option(FilingMode.annual, "-m", "--mode"),
    start_date: str | None = typer.Option(None, "-s", "--start"),
) -> None:
    """Run SEC filing summarization pipeline."""
    load_dotenv()

    data_pkg = files("sec_nlp") / "data"
    with as_file(data_pkg) as data_dir:
        output_folder = Path(data_dir) / "output"
        downloads_folder = Path(data_dir) / "downloads"
        output_folder.mkdir(parents=True, exist_ok=True)
        downloads_folder.mkdir(parents=True, exist_ok=True)

    if not symbols:
        symbols = ["AAPL"]

    _config_kwargs = {
        "pipeline_type": "summary",
        "symbols": symbols,
        "mode": mode,
        "start_date": start_date,
    }
