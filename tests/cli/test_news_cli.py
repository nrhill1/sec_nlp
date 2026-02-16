"""Tests for news CLI wiring."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock, patch

from sec_nlp.cli.commands.news import News
from sec_nlp.pipelines.presets.news import NewsSettings


def test_news_inherits_from_news_settings() -> None:
    assert issubclass(News, NewsSettings)


def test_news_basic_configuration(tmp_path: Path) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    cmd = News(
        email="test@example.com",
        dl_path=dl_path,
        out_path=out_path,
        symbols=["aapl"],
        topics=["supply", "recall"],
        days=45,
        output_format="yaml",
    )

    assert cmd.symbols == ["AAPL"]
    assert cmd.topics == ["supply", "recall"]
    assert cmd.days == 45
    assert cmd.output_format == "yaml"


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline")
def test_news_cli_cmd_execution(
    mock_run_pipeline: Mock, tmp_path: Path
) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    cmd = News(
        email="test@example.com",
        dl_path=dl_path,
        out_path=out_path,
    )
    cmd.cli_cmd()
    mock_run_pipeline.assert_called_once()


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline", autospec=True)
def test_news_cli_integration(mock_run_pipeline: Mock, tmp_path: Path) -> None:
    from pydantic_settings import CliApp

    from sec_nlp.cli.commands import Root

    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    sys.argv = [
        "cli",
        "news",
        "AAPL",
        "--email",
        "test@example.com",
        "--dl-path",
        str(dl_path),
        "--out-path",
        str(out_path),
        "--topics",
        "supply",
        "--topics",
        "recall",
        "--days",
        "30",
        "--output-format",
        "json",
    ]

    CliApp.run(Root)
    assert mock_run_pipeline.called
    config = mock_run_pipeline.call_args[0][0]
    assert config.symbols == ["AAPL"]
    assert config.topics == ["supply", "recall"]
    assert config.days == 30
    assert config.output_format == "json"
