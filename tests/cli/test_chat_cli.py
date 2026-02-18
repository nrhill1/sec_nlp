"""Tests for chat CLI wiring."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from sec_nlp.cli.commands.chat import Chat
from sec_nlp.pipelines.presets.chat import ChatSettings


def test_chat_inherits_from_chat_settings() -> None:
    assert issubclass(Chat, ChatSettings)


def test_chat_basic_configuration(tmp_path: Path) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    cmd = Chat(
        email="test@example.com",
        dl_path=dl_path,
        out_path=out_path,
        symbols=["cde"],
        question="What changed in liquidity?",
        collections=["retrieve", "analyze"],
        top_k=12,
        strict_citations=True,
    )

    assert cmd.symbols == ["CDE"]
    assert cmd.question == "What changed in liquidity?"
    assert cmd.collections == ["retrieve", "analyze"]
    assert cmd.top_k == 12


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline")
def test_chat_cli_cmd_execution(
    mock_run_pipeline: Mock, tmp_path: Path
) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir()
    out_path.mkdir()

    cmd = Chat(
        email="test@example.com",
        dl_path=dl_path,
        out_path=out_path,
        symbols=["CDE"],
        question="Summarize debt covenants",
    )
    cmd.cli_cmd()
    mock_run_pipeline.assert_called_once()


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline", autospec=True)
def test_chat_cli_integration_with_symbol(
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
        "chat",
        "CDE",
        "--email",
        "test@example.com",
        "--dl-path",
        str(dl_path),
        "--out-path",
        str(out_path),
        "--question",
        "What changed in liquidity risk?",
        "--collections",
        "retrieve",
        "--collections",
        "analyze",
        "--forms",
        "6-K",
        "--start-date",
        "2024-01-01",
        "--end-date",
        "2024-12-31",
        "--rerank-mode",
        "mmr",
        "--prefetch-retrieve",
        "--prefetch-queries",
        "neodymium pricing",
        "--include-market-context",
        "--include-news-context",
        "--top-k",
        "7",
    ]

    CliApp.run(Root)
    assert mock_run_pipeline.called
    config = mock_run_pipeline.call_args[0][0]
    assert config.symbols == ["CDE"]
    assert config.question == "What changed in liquidity risk?"
    assert config.collections == ["retrieve", "analyze"]
    assert config.forms == ["6-K"]
    assert config.start_date == date(2024, 1, 1)
    assert config.end_date == date(2024, 12, 31)
    assert config.rerank_mode == "mmr"
    assert config.prefetch_retrieve is True
    assert config.prefetch_queries == ["neodymium pricing"]
    assert config.include_market_context is True
    assert config.include_news_context is True
    assert config.top_k == 7


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline", autospec=True)
def test_chat_cli_integration_without_symbol(
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
        "chat",
        "--email",
        "test@example.com",
        "--dl-path",
        str(dl_path),
        "--out-path",
        str(out_path),
        "--question",
        "Which filings mention refinancing risk?",
    ]

    CliApp.run(Root)
    assert mock_run_pipeline.called
    config = mock_run_pipeline.call_args[0][0]
    assert config.symbols == []
    assert config.question == "Which filings mention refinancing risk?"


@patch("sec_nlp.cli.command.BasePipelineCommand._run_pipeline", autospec=True)
def test_chat_cli_llm_override_preserves_pipeline_defaults(
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
        "chat",
        "MP",
        "--email",
        "test@example.com",
        "--dl-path",
        str(dl_path),
        "--out-path",
        str(out_path),
        "--question",
        "What changed?",
        "--llm.model-name",
        "ministral-3:3b",
    ]

    CliApp.run(Root)
    assert mock_run_pipeline.called
    config = mock_run_pipeline.call_args[0][0]
    assert config.llm.model_name == "ministral-3:3b"
    assert config.llm.require_json is False
    assert config.llm.temperature == 0.1
