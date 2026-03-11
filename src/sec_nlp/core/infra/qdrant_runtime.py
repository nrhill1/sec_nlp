# src/sec_nlp/core/infra/qdrant_runtime.py
"""Helpers for probing and bootstrapping local Docker-backed Qdrant.

These helpers support the default localhost Qdrant workflow used by the
vector-backed pipelines. When the configured endpoint points at local Docker,
the runtime first tries to reach ``localhost:6333`` directly, then attempts a
best-effort bootstrap via ``colima start`` followed by ``sec-nlp qdrant up``.
Callers remain responsible for falling back to disk-backed or in-memory
storage when the Docker endpoint never becomes reachable.
"""

import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Sequence
from urllib.parse import urlparse

from sec_nlp.core.infra.logger import logger

_LOCAL_QDRANT_HOSTS = frozenset({"localhost", "127.0.0.1"})
_DEFAULT_QDRANT_HTTP_PORT = 6333
_PING_TIMEOUT_SECONDS = 0.5
_POLL_INTERVAL_SECONDS = 0.25

type Command = tuple[str, ...]


def is_local_docker_qdrant_target(
    *,
    location: str | None,
    url: str | None,
    host: str,
    port: int,
    https: bool,
) -> bool:
    """Return whether the target points at the default local Docker Qdrant.

    Args:
        location: Explicit Qdrant path or ``:memory:`` override, if any.
        url: Optional Qdrant URL override.
        host: Qdrant host from vector config.
        port: Qdrant HTTP port from vector config.
        https: Whether HTTPS is enabled for the target.

    Returns:
        ``True`` when the connection target is the standard local Docker
        endpoint and should be eligible for Colima/Qdrant auto-start.
    """
    if location is not None or https:
        return False

    if url is not None:
        parsed = urlparse(url)
        if parsed.scheme not in {"", "http"}:
            return False
        parsed_host = parsed.hostname
        parsed_port = parsed.port or _DEFAULT_QDRANT_HTTP_PORT
        return (
            isinstance(parsed_host, str)
            and parsed_host in _LOCAL_QDRANT_HOSTS
            and parsed_port == _DEFAULT_QDRANT_HTTP_PORT
        )

    return host in _LOCAL_QDRANT_HOSTS and port == _DEFAULT_QDRANT_HTTP_PORT


def ping_tcp_port(
    host: str,
    port: int,
    *,
    timeout_seconds: float = _PING_TIMEOUT_SECONDS,
) -> bool:
    """Return whether a TCP endpoint is immediately reachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def wait_for_tcp_port(
    host: str,
    port: int,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float = _POLL_INTERVAL_SECONDS,
) -> bool:
    """Poll a TCP endpoint until it becomes reachable or timeout expires."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if ping_tcp_port(host, port):
            return True
        time.sleep(poll_interval_seconds)
    return False


def _run_command(
    command: Sequence[str],
) -> subprocess.CompletedProcess[str] | None:
    """Run a startup command and return its completed process.

    Missing executables are treated as a soft failure because callers still
    have lower-priority local fallback targets available.
    """
    try:
        return subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        logger.debug("Startup command unavailable: %s", " ".join(command))
        return None


def _command_succeeded(result: subprocess.CompletedProcess[str] | None) -> bool:
    """Return whether a command completed successfully or was already active."""
    if result is None:
        return False
    if result.returncode == 0:
        return True

    output = " ".join(
        part.strip().lower()
        for part in (result.stdout, result.stderr)
        if isinstance(part, str) and part.strip()
    )
    return "already running" in output


def _log_command_failure(
    command: Sequence[str],
    result: subprocess.CompletedProcess[str] | None,
) -> None:
    """Write debug details for a failed startup command."""
    if result is None:
        return
    stderr = result.stderr.strip()
    stdout = result.stdout.strip()
    details = stderr or stdout or f"exit={result.returncode}"
    logger.debug("Command failed (%s): %s", " ".join(command), details)


def _colima_start_command() -> Command:
    """Build the Colima startup command."""
    return ("colima", "start")


def _qdrant_up_command(readiness_timeout: int) -> Command:
    """Build the preferred command for starting Docker-backed Qdrant."""
    uv_executable = shutil.which("uv")
    timeout_value = str(readiness_timeout)
    if uv_executable is not None:
        return (
            uv_executable,
            "run",
            "sec-nlp",
            "qdrant",
            "up",
            "--readiness-timeout",
            timeout_value,
        )
    return (
        sys.executable,
        "-m",
        "sec_nlp",
        "qdrant",
        "up",
        "--readiness-timeout",
        timeout_value,
    )


def ensure_local_docker_qdrant(*, readiness_timeout: int) -> bool:
    """Attempt to make the local Docker Qdrant endpoint reachable.

    The sequence is:
    1. Ping ``localhost:6333`` directly.
    2. Best-effort ``colima start``.
    3. Ping again briefly in case Docker was already serving Qdrant.
    4. Run ``sec-nlp qdrant up`` and wait for readiness.

    Args:
        readiness_timeout: Maximum seconds to wait for the endpoint after the
            explicit Qdrant startup command runs.

    Returns:
        ``True`` when ``localhost:6333`` becomes reachable, otherwise ``False``.
    """
    if ping_tcp_port("127.0.0.1", _DEFAULT_QDRANT_HTTP_PORT):
        return True

    colima_command = _colima_start_command()
    colima_result = _run_command(colima_command)
    if not _command_succeeded(colima_result):
        _log_command_failure(colima_command, colima_result)

    if wait_for_tcp_port(
        "127.0.0.1",
        _DEFAULT_QDRANT_HTTP_PORT,
        timeout_seconds=1.0,
    ):
        return True

    qdrant_command = _qdrant_up_command(readiness_timeout)
    logger.info(
        "Attempting local Docker Qdrant bootstrap via %s",
        " ".join(qdrant_command),
    )
    qdrant_result = _run_command(qdrant_command)
    if not _command_succeeded(qdrant_result):
        _log_command_failure(qdrant_command, qdrant_result)

    return wait_for_tcp_port(
        "127.0.0.1",
        _DEFAULT_QDRANT_HTTP_PORT,
        timeout_seconds=float(readiness_timeout),
    )
