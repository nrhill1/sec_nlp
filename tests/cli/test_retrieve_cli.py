# tests/cli/test_retrieve_cli.py
"""Tests for retrieve CLI wiring."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
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

    cmd = Retrieve.model_validate(
        {
            "email": "test@example.com",
            "dl_path": dl_path,
            "out_path": out_path,
            "symbols": ["aapl"],
            "queries": ["risk"],
            "sections": [7, "item 1a"],
        }
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
        "--hydrate-top-n",
        "12",
        "--query-term-min-hits",
        "2",
        "--query-term-min-ratio",
        "0.5",
        "--no-qdrant-upsert-wait",
        "--output-format",
        "json",
    ]

    CliApp.run(Root)
    assert mock_run_pipeline.called
    config = mock_run_pipeline.call_args[0][0]
    assert config.symbols == ["AAPL"]
    assert config.queries == ["supply chain disruption", "warranty accrual"]
    assert config.top_k == 15
    assert config.hydrate_top_n == 12
    assert config.query_term_min_hits == 2
    assert config.query_term_min_ratio == 0.5
    assert config.qdrant_upsert_wait is False
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


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline", autospec=True)
def test_retrieve_cli_integration_with_semantic_chunking_flags(
    mock_run_pipeline: Mock, tmp_path: Path
) -> None:
    """Nested semantic chunking flags parse correctly from CLI."""
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
        "--semantic-chunking.enabled",
        "--semantic-chunking.embedding-model",
        "qwen3-embedding:4b",
        "--semantic-chunking.breakpoint-threshold-type",
        "gradient",
        "--semantic-chunking.breakpoint-threshold-amount",
        "4.5",
    ]

    CliApp.run(Root)
    assert mock_run_pipeline.called
    config = mock_run_pipeline.call_args[0][0]
    assert config.semantic_chunking.enabled is True
    assert config.semantic_chunking.embedding_model == "qwen3-embedding:4b"
    assert config.semantic_chunking.breakpoint_threshold_type == "gradient"
    assert config.semantic_chunking.breakpoint_threshold_amount == 4.5


def test_retrieve_logs_run_details_in_config_header(
    tmp_path: Path,
    caplog,
) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    cmd = Retrieve(
        email="test@example.com",
        dl_path=dl_path,
        out_path=out_path,
        symbols=["AAPL"],
        queries=["supply chain"],
        top_k=12,
        efts_candidates=150,
        index_results=True,
    )

    caplog.set_level(logging.INFO, logger="sec_nlp")
    cmd._log_config_details()

    assert "Run ID" in caplog.text
    assert "Date Range" in caplog.text
    assert "Queries" in caplog.text
    assert "Collection" in caplog.text
