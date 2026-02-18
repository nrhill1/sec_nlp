"""Tests for insider CLI wiring."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock, patch

from sec_nlp.cli.commands.insider import Insider
from sec_nlp.pipelines.presets.insider import InsiderSettings


def test_insider_inherits_from_insider_settings() -> None:
    assert issubclass(Insider, InsiderSettings)


def test_insider_basic_configuration(tmp_path: Path) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    cmd = Insider(
        email="test@example.com",
        dl_path=dl_path,
        out_path=out_path,
        symbols=["aapl"],
        lookback_months=18,
        output_format="json",
    )

    assert cmd.symbols == ["AAPL"]
    assert cmd.lookback_months == 18
    assert cmd.output_format == "json"
    assert Insider.parse_lookback_months("18m") == 18


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline")
def test_insider_cli_cmd_execution(
    mock_run_pipeline: Mock, tmp_path: Path
) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    cmd = Insider(
        email="test@example.com",
        dl_path=dl_path,
        out_path=out_path,
    )
    cmd.cli_cmd()
    mock_run_pipeline.assert_called_once()


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline", autospec=True)
def test_insider_cli_integration(
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
        "insider",
        "AAPL",
        "--email",
        "test@example.com",
        "--dl-path",
        str(dl_path),
        "--out-path",
        str(out_path),
        "--lookback-months",
        "6",
        "--alert-cluster-threshold",
        "4",
    ]

    CliApp.run(Root)
    assert mock_run_pipeline.called
    config = mock_run_pipeline.call_args[0][0]
    assert config.symbols == ["AAPL"]
    assert config.lookback_months == 6
    assert config.alert_cluster_threshold == 4
