# tests/cli/test_flow_cli.py
"""Tests for flow CLI wiring and argument handling."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock, patch

from pydantic_settings import CliApp
from pytest import CaptureFixture

from sec_nlp.app.flows.models import FlowRunResult, FlowStageResult
from sec_nlp.cli.commands.flow import FlowRun, FlowValidate


def _write_flow_spec(tmp_path: Path) -> Path:
    """Create a minimal retrieve->chat flow spec fixture."""
    spec_path = tmp_path / "flow_spec.yaml"
    spec_path.write_text(
        "\n".join(
            [
                "name: test_flow",
                "defaults:",
                "  email: test@example.com",
                "stages:",
                "  - id: retrieve_seed",
                "    pipeline: retrieve",
                "    overrides:",
                "      queries: [liquidity risk]",
                "      output_format: json",
                "  - id: chat_answer",
                "    pipeline: chat",
                "    inputs:",
                "    - from_stage: retrieve_seed",
                "      artifact: retrieve_seed",
                "      target_field: seed_context",
                "    overrides:",
                "      question: What changed in liquidity risk?",
                "      interactive: false",
                "      output_format: json",
            ]
        ),
        encoding="utf-8",
    )
    return spec_path


@patch("sec_nlp.cli.commands.flow.logger")
def test_flow_validate_cli_cmd(mock_logger: Mock, tmp_path: Path) -> None:
    spec_path = _write_flow_spec(tmp_path)

    FlowValidate(spec=spec_path).cli_cmd()

    info_messages = [
        str(call.args[0])
        for call in mock_logger.info.call_args_list
        if call.args
    ]
    assert any("Flow spec is valid" in message for message in info_messages)


@patch("sec_nlp.cli.commands.flow.FlowRunner.run")
def test_flow_run_cli_cmd_uses_runner(
    mock_flow_run: Mock,
    tmp_path: Path,
) -> None:
    spec_path = _write_flow_spec(tmp_path)
    mock_flow_run.return_value = FlowRunResult(
        flow_run_id="00000000-0000-0000-0000-00000000abcd",
        flow_name="test_flow",
        success=True,
        stage_results=[],
        outputs=[],
        metadata={},
    )

    FlowRun(spec=spec_path).cli_cmd()

    assert mock_flow_run.called


@patch("sec_nlp.cli.commands.flow.logger")
@patch("sec_nlp.cli.commands.flow.FlowRunner.run")
def test_flow_run_logs_chat_answer_snippet(
    mock_flow_run: Mock,
    mock_logger: Mock,
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    spec_path = _write_flow_spec(tmp_path)
    mock_flow_run.return_value = FlowRunResult(
        flow_run_id="00000000-0000-0000-0000-00000000abcf",
        flow_name="test_flow",
        success=True,
        stage_results=[
            FlowStageResult(
                stage_id="chat_answer",
                pipeline="chat",
                success=True,
                metadata={
                    "answer_preview": "Liquidity risk rose after debt repricing.",
                    "answer_output_paths": [
                        "/tmp/chat_summary.json",
                        "/tmp/chat_summary.yaml",
                    ],
                },
            )
        ],
        outputs=[],
        metadata={
            "answer_output_paths": [
                "/tmp/chat_summary.json",
                "/tmp/chat_summary.yaml",
            ]
        },
    )

    FlowRun(spec=spec_path).cli_cmd()
    captured = capsys.readouterr()

    info_messages = [
        str(call.args[0])
        for call in mock_logger.info.call_args_list
        if call.args
    ]
    assert any("Answer Snippet" in message for message in info_messages)
    assert any("Answer File" in message for message in info_messages)
    assert any("/tmp/chat_summary.json" in message for message in info_messages)
    assert any("Answer Files" in message for message in info_messages)
    assert captured.out.splitlines() == [
        "/tmp/chat_summary.json",
        "/tmp/chat_summary.yaml",
    ]


@patch("sec_nlp.cli.commands.flow.FlowRunner.run")
def test_flow_cli_integration_run_subcommand(
    mock_flow_run: Mock,
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    from sec_nlp.cli.commands import Root

    spec_path = _write_flow_spec(tmp_path)
    mock_flow_run.return_value = FlowRunResult(
        flow_run_id="00000000-0000-0000-0000-00000000abce",
        flow_name="test_flow",
        success=True,
        stage_results=[],
        outputs=[],
        metadata={"answer_output_paths": ["/tmp/chat_summary.json"]},
    )

    sys.argv = [
        "cli",
        "flow",
        "run",
        "--spec",
        str(spec_path),
    ]
    CliApp.run(Root)
    captured = capsys.readouterr()

    assert mock_flow_run.called
    assert captured.out.splitlines() == ["/tmp/chat_summary.json"]
