# tests/test_local_docker_stack.py
"""Tests for the local Docker Compose development stack definition."""

from pathlib import Path

import yaml


def _repo_root() -> Path:
    """Return the repository root for Docker stack fixtures."""
    return Path(__file__).resolve().parents[1]


def test_compose_stack_defines_background_app_and_qdrant() -> None:
    """Validate the local Compose stack shape and single-command entrypoint."""
    compose_path = _repo_root() / "compose.yaml"
    payload = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    assert payload["name"] == "sec-benchmark-local"
    assert payload["services"]["benchmark-runner"]["command"] == [
        "sleep",
        "infinity",
    ]
    assert payload["services"]["benchmark-runner"]["entrypoint"] == [
        "/usr/local/bin/sec-nlp-dev-entrypoint"
    ]
    assert (
        payload["services"]["benchmark-runner"]["environment"][
            "SEC_NLP_CONTAINER_LOG_DIR"
        ]
        == "/workspace/logs/container/benchmark-runner"
    )
    assert payload["services"]["qdrant"]["image"] == "qdrant/qdrant:v1.13.6"


def test_local_docker_artifacts_exist() -> None:
    """Ensure the Compose stack references checked-in Docker assets."""
    repo_root = _repo_root()

    assert (repo_root / "docker" / "Dockerfile.local").is_file()
    assert (repo_root / "docker" / "dev-entrypoint.sh").is_file()
    assert (repo_root / ".dockerignore").is_file()
