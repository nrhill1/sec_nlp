"""Tests for events CLI wiring."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock, patch

from sec_nlp.cli.commands.events import Events
from sec_nlp.pipelines.presets.events import EventsSettings


def test_events_inherits_from_events_settings() -> None:
    assert issubclass(Events, EventsSettings)


def test_events_basic_configuration(tmp_path: Path) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    cmd = Events(
        email="test@example.com",
        dl_path=dl_path,
        out_path=out_path,
        symbols=["aapl"],
        event_types=["executive", "restatement"],
        lookback_years=3,
        output_format="yaml",
    )

    assert cmd.symbols == ["AAPL"]
    assert cmd.event_types == ["executive", "restatement"]
    assert cmd.lookback_years == 3
    assert cmd.output_format == "yaml"


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline")
def test_events_cli_cmd_execution(
    mock_run_pipeline: Mock, tmp_path: Path
) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    cmd = Events(
        email="test@example.com",
        dl_path=dl_path,
        out_path=out_path,
    )
    cmd.cli_cmd()
    mock_run_pipeline.assert_called_once()


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline", autospec=True)
def test_events_cli_integration(
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
        "events",
        "AAPL",
        "--email",
        "test@example.com",
        "--dl-path",
        str(dl_path),
        "--out-path",
        str(out_path),
        "--event-types",
        "executive",
        "--event-types",
        "restatement",
        "--lookback-years",
        "4",
        "--output-format",
        "json",
    ]

    CliApp.run(Root)
    assert mock_run_pipeline.called
    config = mock_run_pipeline.call_args[0][0]
    assert config.symbols == ["AAPL"]
    assert config.event_types == ["executive", "restatement"]
    assert config.lookback_years == 4
    assert config.output_format == "json"
