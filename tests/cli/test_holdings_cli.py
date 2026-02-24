# tests/cli/test_holdings_cli.py
"""Tests for holdings CLI wiring."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock, patch

from sec_nlp.cli.commands.holdings import Holdings
from sec_nlp.pipelines.presets.holdings import HoldingsSettings


def test_holdings_inherits_from_holdings_settings() -> None:
    assert issubclass(Holdings, HoldingsSettings)


def test_holdings_basic_configuration(tmp_path: Path) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    cmd = Holdings(
        email="test@example.com",
        dl_path=dl_path,
        out_path=out_path,
        symbols=["aapl"],
        quarters=6,
        output_format="json",
        top_holders=10,
    )

    assert cmd.symbols == ["AAPL"]
    assert cmd.quarters == 6
    assert cmd.output_format == "json"
    assert cmd.top_holders == 10


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline")
def test_holdings_cli_cmd_execution(
    mock_run_pipeline: Mock, tmp_path: Path
) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    cmd = Holdings(
        email="test@example.com",
        dl_path=dl_path,
        out_path=out_path,
    )
    cmd.cli_cmd()
    mock_run_pipeline.assert_called_once()


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline", autospec=True)
def test_holdings_cli_integration(
    mock_run_pipeline: Mock, tmp_path: Path
) -> None:
    from pydantic_settings import CliApp

    from sec_nlp.cli.commands import Root

    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    sys.argv = [
        "cli",
        "holdings",
        "AAPL",
        "--email",
        "test@example.com",
        "--dl-path",
        str(dl_path),
        "--out-path",
        str(out_path),
        "--quarters",
        "3",
        "--top-holders",
        "15",
    ]

    CliApp.run(Root)
    assert mock_run_pipeline.called
    config = mock_run_pipeline.call_args[0][0]
    assert config.symbols == ["AAPL"]
    assert config.quarters == 3
    assert config.top_holders == 15
