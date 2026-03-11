# tests/core/test_qdrant_runtime.py
"""Tests for local Docker Qdrant bootstrap helpers."""

import subprocess

import pytest

from sec_nlp.core.infra import qdrant_runtime


def test_is_local_docker_qdrant_target_matches_default_localhost() -> None:
    """Return true for the default localhost Docker endpoint."""
    assert qdrant_runtime.is_local_docker_qdrant_target(
        location=None,
        url=None,
        host="localhost",
        port=6333,
        https=False,
    )


def test_is_local_docker_qdrant_target_rejects_explicit_location() -> None:
    """Return false when a path-backed Qdrant location is configured."""
    assert not qdrant_runtime.is_local_docker_qdrant_target(
        location=".qdrant",
        url=None,
        host="localhost",
        port=6333,
        https=False,
    )


def test_ensure_local_docker_qdrant_returns_immediately_when_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Skip startup commands when localhost:6333 is already reachable."""
    commands: list[tuple[str, ...]] = []

    monkeypatch.setattr(
        qdrant_runtime, "ping_tcp_port", lambda *_args, **_kwargs: True
    )
    monkeypatch.setattr(
        qdrant_runtime,
        "_run_command",
        lambda command: commands.append(tuple(command)) or None,
    )

    assert qdrant_runtime.ensure_local_docker_qdrant(readiness_timeout=3)
    assert commands == []


def test_ensure_local_docker_qdrant_runs_colima_then_qdrant_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run Colima startup before `sec-nlp qdrant up` when localhost is down."""
    commands: list[tuple[str, ...]] = []

    monkeypatch.setattr(
        qdrant_runtime, "ping_tcp_port", lambda *_args, **_kwargs: False
    )
    waits = iter([False, True])
    monkeypatch.setattr(
        qdrant_runtime,
        "wait_for_tcp_port",
        lambda *_args, **_kwargs: next(waits),
    )

    def _run_command(
        command: tuple[str, ...],
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(
            args=list(command),
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(qdrant_runtime, "_run_command", _run_command)
    monkeypatch.setattr(
        qdrant_runtime,
        "_qdrant_up_command",
        lambda timeout: (
            "uv",
            "run",
            "sec-nlp",
            "qdrant",
            "up",
            "--readiness-timeout",
            str(timeout),
        ),
    )

    assert qdrant_runtime.ensure_local_docker_qdrant(readiness_timeout=4)
    assert commands == [
        ("colima", "start"),
        (
            "uv",
            "run",
            "sec-nlp",
            "qdrant",
            "up",
            "--readiness-timeout",
            "4",
        ),
    ]


def test_ensure_local_docker_qdrant_reports_failure_after_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return false when localhost never becomes reachable."""
    monkeypatch.setattr(
        qdrant_runtime, "ping_tcp_port", lambda *_args, **_kwargs: False
    )
    monkeypatch.setattr(
        qdrant_runtime,
        "wait_for_tcp_port",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        qdrant_runtime,
        "_run_command",
        lambda command: subprocess.CompletedProcess(
            args=list(command),
            returncode=1,
            stdout="",
            stderr="failed",
        ),
    )
    monkeypatch.setattr(
        qdrant_runtime,
        "_qdrant_up_command",
        lambda timeout: (
            "uv",
            "run",
            "sec-nlp",
            "qdrant",
            "up",
            "--readiness-timeout",
            str(timeout),
        ),
    )

    assert not qdrant_runtime.ensure_local_docker_qdrant(readiness_timeout=2)
