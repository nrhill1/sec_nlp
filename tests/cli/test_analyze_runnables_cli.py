"""Tests for analyze runnable CLI command variants."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock, patch


@patch(
    "sec_nlp.cli.command.BasePipelineCommand._should_collect_metrics",
    return_value=False,
)
@patch(
    "sec_nlp.cli.command.BasePipelineCommand._should_validate",
    return_value=False,
)
@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline", autospec=True)
def test_analyze_search_cli_sets_expected_runnables(
    mock_run_pipeline: Mock,
    _mock_should_validate: Mock,
    _mock_should_collect_metrics: Mock,
    tmp_path: Path,
) -> None:
    from pydantic_settings import CliApp

    from sec_nlp.cli.commands import Root
    from sec_nlp.cli.commands.analyze_runnables import AnalyzeSearchCommand

    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    sys.argv = [
        "cli",
        "scan",
        "AAPL",
        "--email",
        "test@example.com",
        "--dl-path",
        str(dl_path),
        "--out-path",
        str(out_path),
    ]

    CliApp.run(Root)

    command_instance = mock_run_pipeline.call_args[0][0]
    assert isinstance(command_instance, AnalyzeSearchCommand)
    assert command_instance.runnables == ["search", "export"]


@patch(
    "sec_nlp.cli.command.BasePipelineCommand._should_collect_metrics",
    return_value=False,
)
@patch(
    "sec_nlp.cli.command.BasePipelineCommand._should_validate",
    return_value=False,
)
@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline", autospec=True)
def test_analyze_analysis_cli_sets_expected_runnables(
    mock_run_pipeline: Mock,
    _mock_should_validate: Mock,
    _mock_should_collect_metrics: Mock,
    tmp_path: Path,
) -> None:
    from pydantic_settings import CliApp

    from sec_nlp.cli.commands import Root
    from sec_nlp.cli.commands.analyze_runnables import AnalyzeAnalysisCommand

    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    sys.argv = [
        "cli",
        "brief",
        "MSFT",
        "--email",
        "test@example.com",
        "--dl-path",
        str(dl_path),
        "--out-path",
        str(out_path),
    ]

    CliApp.run(Root)

    command_instance = mock_run_pipeline.call_args[0][0]
    assert isinstance(command_instance, AnalyzeAnalysisCommand)
    assert command_instance.runnables == ["search", "analysis", "export"]


@patch(
    "sec_nlp.cli.command.BasePipelineCommand._should_collect_metrics",
    return_value=False,
)
@patch(
    "sec_nlp.cli.command.BasePipelineCommand._should_validate",
    return_value=False,
)
@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline", autospec=True)
def test_analyze_market_correlation_cli_sets_expected_defaults(
    mock_run_pipeline: Mock,
    _mock_should_validate: Mock,
    _mock_should_collect_metrics: Mock,
    tmp_path: Path,
) -> None:
    from pydantic_settings import CliApp

    from sec_nlp.cli.commands import Root
    from sec_nlp.cli.commands.analyze_runnables import (
        AnalyzeMarketCorrelationCommand,
    )

    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    sys.argv = [
        "cli",
        "pulse",
        "CDE",
        "--email",
        "test@example.com",
        "--dl-path",
        str(dl_path),
        "--out-path",
        str(out_path),
    ]

    CliApp.run(Root)

    command_instance = mock_run_pipeline.call_args[0][0]
    assert isinstance(command_instance, AnalyzeMarketCorrelationCommand)
    assert command_instance.prompt == "market_correlation"
    assert command_instance.runnables == [
        "search",
        "analysis",
        "export",
        "market_correlation",
    ]
