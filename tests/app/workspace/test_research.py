# tests/app/workspace/test_research.py
"""Tests for research worker ownership, cancellation, and explicit failure records."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from sec_nlp.app.workspace.research import execute_research
from sec_nlp.app.workspace.store import WorkspaceStore


def test_worker_start_failure_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Leave a visible failed job when the selected process cannot be launched."""
    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        AsyncMock(side_effect=OSError("cannot launch")),
    )
    store = WorkspaceStore(tmp_path)
    with pytest.raises(OSError, match="cannot launch"):
        asyncio.run(
            execute_research(store, "financials", {"symbols": ["AAPL"]})
        )
    assert store.list_jobs()[0].status == "error"


def test_cancellation_terminates_owned_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wait for child termination before recording cancellation in the workspace."""
    process = MagicMock(spec=asyncio.subprocess.Process)
    process.returncode = None
    process.communicate = AsyncMock(side_effect=asyncio.CancelledError)
    process.wait = AsyncMock(return_value=0)
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )
    store = WorkspaceStore(tmp_path)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            execute_research(store, "financials", {"symbols": ["AAPL"]})
        )
    process.terminate.assert_called_once()
    process.wait.assert_awaited_once()
    assert store.list_jobs()[0].status == "cancelled"
