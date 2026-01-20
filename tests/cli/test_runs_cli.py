# tests/cli/test_runs_cli.py
"""Tests for the runs CLI commands."""

import logging
from datetime import UTC, datetime, timedelta

import pytest

from sec_nlp.cli.commands.runs import RunsLs
from sec_nlp.pipelines.observability.run_registry import RunRecord


class _StubRegistry:
    def __init__(self, runs: list[RunRecord]) -> None:
        self._runs = runs

    def list_runs(
        self, pipeline_type: str | None, status: str | None, limit: int
    ) -> list[RunRecord]:
        return self._runs[:limit]


@pytest.fixture
def sample_runs() -> list[RunRecord]:
    now = datetime.now(UTC)
    return [
        # Should render as incomplete (running with no completion)
        RunRecord(
            record_id=1,
            run_id="run-incomplete",
            pipeline_type="exhibit",
            started_at=now - timedelta(hours=2),
            completed_at=None,
            status="running",
            output_dir=None,
            metadata=None,
        ),
        # Should normalize to completed even if status is still "running"
        RunRecord(
            record_id=2,
            run_id="run-finished",
            pipeline_type="exhibit",
            started_at=now - timedelta(hours=3),
            completed_at=now - timedelta(hours=2, minutes=30),
            status="running",
            output_dir=None,
            metadata=None,
        ),
        # Failed run stays failed
        RunRecord(
            record_id=3,
            run_id="run-failed",
            pipeline_type="exhibit",
            started_at=now - timedelta(hours=4),
            completed_at=now - timedelta(hours=3, minutes=50),
            status="failed",
            output_dir=None,
            metadata=None,
        ),
    ]


def test_runs_ls_marks_incomplete(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    sample_runs: list[RunRecord],
) -> None:
    """Ensure incomplete runs aren't displayed as running."""
    registry = _StubRegistry(sample_runs)
    monkeypatch.setattr(
        "sec_nlp.cli.commands.runs.get_registry", lambda: registry
    )

    caplog.set_level(logging.INFO, logger="sec_nlp")

    cmd = RunsLs()
    cmd.cli_cmd()

    log_text = caplog.text.lower()

    assert "incomplete" in log_text
    assert "completed" in log_text
    assert "failed" in log_text
    # The only occurrence of "running" should be within metadata or IDs, not as a status
    assert " running " not in log_text
