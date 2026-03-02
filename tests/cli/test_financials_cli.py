# tests/cli/test_financials_cli.py
"""Tests for financials CLI wiring."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock, patch

from sec_nlp.cli.commands.financials import Financials
from sec_nlp.pipelines.presets.financials import FinancialsSettings


def test_financials_inherits_from_financials_settings() -> None:
    assert issubclass(Financials, FinancialsSettings)


def test_financials_basic_configuration(tmp_path: Path) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    cmd = Financials(
        email="test@example.com",
        dl_path=dl_path,
        out_path=out_path,
        symbols=["aapl"],
        periods=6,
        output_format="json",
    )

    assert cmd.symbols == ["AAPL"]
    assert cmd.periods == 6
    assert cmd.output_format == "json"


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline")
def test_financials_cli_cmd_execution(
    mock_run_pipeline: Mock, tmp_path: Path
) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    cmd = Financials(
        email="test@example.com",
        dl_path=dl_path,
        out_path=out_path,
    )
    cmd.cli_cmd()
    mock_run_pipeline.assert_called_once()


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline", autospec=True)
def test_financials_cli_integration(
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
        "financials",
        "AAPL",
        "--email",
        "test@example.com",
        "--dl-path",
        str(dl_path),
        "--out-path",
        str(out_path),
        "--periods",
        "5",
        "--output-format",
        "yaml",
    ]

    CliApp.run(Root)
    assert mock_run_pipeline.called
    config = mock_run_pipeline.call_args[0][0]
    assert config.symbols == ["AAPL"]
    assert config.periods == 5
    assert config.output_format == "yaml"
