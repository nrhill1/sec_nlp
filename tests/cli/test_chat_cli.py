"""Tests for chat CLI wiring."""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from sec_nlp.cli.commands.chat import Chat
from sec_nlp.pipelines.presets.chat import ChatResult, ChatSettings


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
        "--market-context-profile",
        "compact",
        "--include-news-context",
        "--context-token-budget",
        "4500",
        "--per-symbol-min-chunks",
        "2",
        "--llm-timeout-seconds",
        "90",
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
    assert config.market_context_profile == "compact"
    assert config.include_news_context is True
    assert config.context_token_budget == 4500
    assert config.per_symbol_min_chunks == 2
    assert config.llm_timeout_seconds == 90
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


def test_chat_handle_result_logs_question_before_answer(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
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
        question="What changed in liquidity risk?",
    )
    result = ChatResult(
        success=True,
        answer="Liquidity risk increased.",
        citation_ids=["C1"],
    )

    caplog.set_level(logging.INFO, logger="sec_nlp")
    cmd._handle_result(result)

    question_pos = caplog.text.find("Question:")
    answer_pos = caplog.text.find("Answer:")
    assert question_pos != -1
    assert answer_pos != -1
    assert question_pos < answer_pos
    assert "What changed in liquidity risk?" in caplog.text


def test_chat_logs_run_details_in_config_header(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
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
        question="What changed in liquidity risk?",
        collections=["retrieve"],
        top_k=9,
    )

    caplog.set_level(logging.INFO, logger="sec_nlp")
    cmd._log_config_details()

    assert "Run ID" in caplog.text
    assert "Date Range" in caplog.text
    assert "Collections" in caplog.text
    assert "Question" in caplog.text
