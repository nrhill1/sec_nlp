# tests/app/workspace/test_research.py
"""Tests for research worker ownership, cancellation, and explicit failure records."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from sec_nlp.app.workspace.research import execute_research
from sec_nlp.app.workspace.store import WorkspaceStore


@pytest.mark.parametrize("failure", ["directory", "profile", "request"])
def test_preparation_failure_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """Record preparation failures before a child process is launched."""
    store = WorkspaceStore(tmp_path)
    launch = AsyncMock()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    match failure:
        case "directory":
            (tmp_path / "research").write_text(
                "directory blocked", encoding="utf-8"
            )
        case "profile":
            (tmp_path / "config.json").write_text(
                "invalid JSON", encoding="utf-8"
            )
        case "request":
            monkeypatch.setattr(
                Path,
                "write_text",
                MagicMock(side_effect=PermissionError("read only")),
            )
    with pytest.raises((OSError, ValueError)) as failure_info:
        asyncio.run(
            execute_research(store, "financials", {"symbols": ["AAPL"]})
        )
    launch.assert_not_awaited()
    job = store.list_jobs()[0]
    assert job.status == "error"
    assert job.message == str(failure_info.value)


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


@pytest.mark.parametrize("already_exited", [False, True])
@pytest.mark.parametrize("force_kill", [False, True])
def test_cancellation_terminates_owned_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    already_exited: bool,
    force_kill: bool,
) -> None:
    """Wait for child termination before recording cancellation in the workspace."""

    async def run() -> None:
        """Cancel an active communication task and optionally race child exit."""
        started = asyncio.Event()
        finished = asyncio.Event()

        async def communicate() -> tuple[bytes, bytes]:
            """Drain the child until termination completes."""
            started.set()
            await finished.wait()
            return b"", b""

        def terminate() -> None:
            """Model normal termination or a child that concurrently finished."""
            if not force_kill:
                finish()

        def finish() -> None:
            """Complete communication before optionally reporting an exit race."""
            finished.set()
            if already_exited:
                raise ProcessLookupError("already exited")

        process = MagicMock(spec=asyncio.subprocess.Process)
        process.returncode = None
        process.communicate = AsyncMock(side_effect=communicate)
        process.terminate = MagicMock(side_effect=terminate)
        process.kill = MagicMock(side_effect=finish)
        if force_kill:
            monkeypatch.setattr(
                asyncio, "wait_for", AsyncMock(side_effect=TimeoutError)
            )
        monkeypatch.setattr(
            asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
        )
        store = WorkspaceStore(tmp_path)
        action = asyncio.create_task(execute_research(store, "financials", {}))
        await started.wait()
        action.cancel()
        with pytest.raises(asyncio.CancelledError):
            await action
        process.terminate.assert_called_once()
        process.communicate.assert_awaited_once()
        assert process.kill.call_count == int(force_kill)
        assert store.list_jobs()[0].status == "cancelled"

    asyncio.run(run())


@pytest.mark.skipif(
    sys.platform == "win32", reason="Uses POSIX SIGTERM handling"
)
def test_cancellation_drains_output_while_child_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drain both pipes when a real terminating child emits more than pipe capacity."""

    async def run() -> None:
        """Cancel the action after the child installs its termination handler."""
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import os, signal\n"
            "def stop(signum, frame):\n"
            "    for channel in (1, 2):\n"
            "        for _ in range(64):\n"
            "            os.write(channel, b'x' * 65536)\n"
            "    raise SystemExit(0)\n"
            "signal.signal(signal.SIGTERM, stop)\n"
            "os.write(1, b'ready\\n')\n"
            "signal.pause()\n",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert child.stdout is not None
        assert (
            await asyncio.wait_for(child.stdout.readline(), timeout=5)
            == b"ready\n"
        )
        launch = AsyncMock(return_value=child)
        monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
        store = WorkspaceStore(tmp_path)
        action = asyncio.create_task(execute_research(store, "financials", {}))
        try:
            await asyncio.sleep(0)
            launch.assert_awaited_once()
            action.cancel()
            completed, _ = await asyncio.wait((action,), timeout=2)
            assert action in completed, (
                "Cancellation stopped draining the child's pipes"
            )
            with pytest.raises(asyncio.CancelledError):
                await action
            assert child.returncode == 0
            assert store.list_jobs()[0].status == "cancelled"
        finally:
            if not action.done():
                action.cancel()
            await asyncio.gather(action, return_exceptions=True)
            if child.returncode is None:
                child.kill()
            await child.communicate()

    asyncio.run(run())
