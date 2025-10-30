# src/sec_nlp/cli/commands/summarize.py
"""Run command - dispatches to summary pipeline."""

from __future__ import annotations

from importlib.resources import as_file, files
from pathlib import Path

import typer

from sec_nlp.core import FilingMode
from sec_nlp.pipelines.summary import SummaryConfig, SummaryPipeline


def summarize_command(
    symbols: list[str] = typer.Argument(
        None,
        help="Stock ticker symbols",
    ),
    mode: FilingMode = typer.Option(FilingMode.annual, "-m", "--mode"),
    start_date: str | None = typer.Option(None, "-s", "--start_date"),
    end_date: str | None = type.Option(None, "-e", "--end_date"),
) -> None:
    """Run SEC filing summarization pipeline."""

    data_dir = files("sec_nlp") / "data"
    with as_file(data_dir) as data:
        output_folder = Path(data) / "output"
        downloads_folder = Path(data) / "downloads"
        output_folder.mkdir(parents=True, exist_ok=True)
        downloads_folder.mkdir(parents=True, exist_ok=True)

    _sc = SummaryConfig()
    _sp = SummaryPipeline()
