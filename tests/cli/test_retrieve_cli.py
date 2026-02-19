"""Tests for retrieve CLI wiring."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch

from sec_nlp.cli.commands.retrieve import Retrieve
from sec_nlp.pipelines.presets.retrieve import RetrieveSettings


def test_retrieve_inherits_from_retrieve_settings() -> None:
    assert issubclass(Retrieve, RetrieveSettings)


def test_retrieve_basic_configuration(tmp_path: Path) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    cmd = Retrieve(
        email="test@example.com",
        dl_path=dl_path,
        out_path=out_path,
        symbols=["aapl"],
        queries=["supply chain", "warranty"],
        top_k=25,
        output_format="yaml",
    )

    assert cmd.symbols == ["AAPL"]
    assert cmd.queries == ["supply chain", "warranty"]
    assert cmd.top_k == 25
    assert cmd.output_format == "yaml"


def test_retrieve_normalizes_numeric_sections(tmp_path: Path) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    cmd = Retrieve(
        email="test@example.com",
        dl_path=dl_path,
        out_path=out_path,
        symbols=["aapl"],
        queries=["risk"],
        sections=cast(list[str], [7, "item 1a"]),
    )

    assert cmd.sections == ["7", "1A"]


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline")
def test_retrieve_cli_cmd_execution(
    mock_run_pipeline: Mock, tmp_path: Path
) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    cmd = Retrieve(
        email="test@example.com",
        dl_path=dl_path,
        out_path=out_path,
        queries=["supply chain"],
    )
    assert cmd.symbols == []
    cmd.cli_cmd()
    mock_run_pipeline.assert_called_once()


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline", autospec=True)
def test_retrieve_cli_integration(
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
        "retrieve",
        "AAPL",
        "--email",
        "test@example.com",
        "--dl-path",
        str(dl_path),
        "--out-path",
        str(out_path),
        "--queries",
        "supply chain disruption",
        "--queries",
        "warranty accrual",
        "--top-k",
        "15",
        "--output-format",
        "json",
    ]

    CliApp.run(Root)
    assert mock_run_pipeline.called
    config = mock_run_pipeline.call_args[0][0]
    assert config.symbols == ["AAPL"]
    assert config.queries == ["supply chain disruption", "warranty accrual"]
    assert config.top_k == 15
    assert config.output_format == "json"


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline", autospec=True)
def test_retrieve_cli_integration_without_symbol(
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
        "retrieve",
        "--email",
        "test@example.com",
        "--dl-path",
        str(dl_path),
        "--out-path",
        str(out_path),
        "--queries",
        "supply chain disruption",
        "--output-format",
        "json",
    ]

    CliApp.run(Root)
    assert mock_run_pipeline.called
    config = mock_run_pipeline.call_args[0][0]
    assert config.symbols == []
    assert config.queries == ["supply chain disruption"]


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline", autospec=True)
def test_retrieve_cli_integration_with_market_signals_flag(
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
        "retrieve",
        "AAPL",
        "--email",
        "test@example.com",
        "--dl-path",
        str(dl_path),
        "--out-path",
        str(out_path),
        "--queries",
        "supply chain disruption",
        "--include-market-signals",
    ]

    CliApp.run(Root)
    assert mock_run_pipeline.called
    config = mock_run_pipeline.call_args[0][0]
    assert config.include_market_signals is True
