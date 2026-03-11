# tests/cli/test_qdrant_cli.py
"""Tests for Qdrant CLI defaults, collection reporting, and startup diagnostics."""

import logging
from dataclasses import dataclass

import pytest
from qdrant_client.models import Distance, VectorParams

from sec_nlp.cli.commands.qdrant import QdrantInfo, QdrantList, QdrantUp
from sec_nlp.types import JsonValue


@dataclass(slots=True, frozen=True)
class _FakeOptimizerConfig:
    """Minimal optimizer config for Qdrant CLI tests."""

    deleted_threshold: float
    indexing_threshold: int


@dataclass(slots=True, frozen=True)
class _FakeCollectionParams:
    """Minimal params container for Qdrant CLI tests."""

    vectors: VectorParams
    on_disk_payload: bool


@dataclass(slots=True, frozen=True)
class _FakeCollectionConfig:
    """Minimal config container for Qdrant CLI tests."""

    params: _FakeCollectionParams
    optimizer_config: _FakeOptimizerConfig | None = None


@dataclass(slots=True, frozen=True)
class _FakeCollectionInfo:
    """Minimal collection info model for Qdrant CLI tests."""

    status: str
    vectors_count: int | None
    points_count: int | None
    indexed_vectors_count: int | None
    config: _FakeCollectionConfig


class _FakeQdrantClient:
    """Minimal Qdrant client stub for collection-info CLI tests."""

    def __init__(self, info: _FakeCollectionInfo) -> None:
        """Store the fake collection info."""
        self._info = info

    def collection_exists(self, collection_name: str) -> bool:
        """Return whether the requested collection exists."""
        _ = collection_name
        return True

    def get_collection(self, collection_name: str) -> _FakeCollectionInfo:
        """Return the fake collection info for the requested collection."""
        _ = collection_name
        return self._info


def test_qdrant_base_defaults_use_localhost_endpoint() -> None:
    """Collection commands should default to localhost Docker endpoint."""
    cmd = QdrantList()
    assert cmd.qdrant_location is None
    assert cmd._get_endpoint_display() == "http://localhost:6333"


def test_qdrant_base_normalizes_none_location_marker() -> None:
    """Explicit null-like CLI values for qdrant_location should unset location."""
    cmd = QdrantList(qdrant_location="none")
    assert cmd.qdrant_location is None
    assert cmd._get_endpoint_display() == "http://localhost:6333"


def test_qdrant_base_setup_client_uses_host_when_location_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Qdrant client construction should use host/port by default."""
    cmd = QdrantList()
    captured: dict[str, JsonValue] = {}
    sentinel = object()

    def _create_qdrant_client(**kwargs: JsonValue) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        "sec_nlp.cli.commands.qdrant.create_qdrant_client",
        _create_qdrant_client,
    )

    client = cmd._setup_qdrant_client()
    assert client is sentinel
    assert captured["location"] is None
    assert captured["url"] is None
    assert captured["host"] == "localhost"
    assert captured["port"] == 6333


def test_qdrant_up_reachable_logs_success(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Detached startup should report success once localhost is reachable."""
    cmd = QdrantUp.model_validate({"detach": True, "readiness_timeout": 1})
    calls: dict[str, int] = {"start": 0, "create": 0, "snapshot": 0}

    monkeypatch.setattr(cmd, "_container_exists", lambda: True)

    def _start_existing_container() -> None:
        calls["start"] += 1

    def _create_container() -> None:
        calls["create"] += 1

    def _log_runtime_snapshot() -> None:
        calls["snapshot"] += 1

    monkeypatch.setattr(
        cmd, "_start_existing_container", _start_existing_container
    )
    monkeypatch.setattr(cmd, "_create_container", _create_container)
    monkeypatch.setattr(cmd, "_wait_for_localhost_http", lambda: True)
    monkeypatch.setattr(cmd, "_log_runtime_snapshot", _log_runtime_snapshot)

    caplog.set_level(logging.INFO, logger="sec_nlp")

    cmd.cli_cmd()

    assert calls == {"start": 1, "create": 0, "snapshot": 1}
    assert "Qdrant started" in caplog.text
    assert "http://localhost:6333" in caplog.text


def test_qdrant_up_unreachable_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Detached startup should fail when localhost remains unreachable."""
    cmd = QdrantUp.model_validate({"detach": True, "readiness_timeout": 1})
    calls: dict[str, int] = {"diagnostics": 0}

    monkeypatch.setattr(cmd, "_container_exists", lambda: True)
    monkeypatch.setattr(cmd, "_start_existing_container", lambda: None)
    monkeypatch.setattr(cmd, "_create_container", lambda: None)
    monkeypatch.setattr(cmd, "_wait_for_localhost_http", lambda: False)

    def _log_unreachable_diagnostics() -> None:
        calls["diagnostics"] += 1

    monkeypatch.setattr(
        cmd, "_log_unreachable_diagnostics", _log_unreachable_diagnostics
    )

    with pytest.raises(RuntimeError, match="localhost:6333"):
        cmd.cli_cmd()

    assert calls["diagnostics"] == 1


def test_unreachable_diagnostics_explain_missing_network(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Diagnostics should explain when no Docker network is attached."""
    cmd = QdrantUp()

    monkeypatch.setattr(cmd, "_container_exists", lambda: True)
    monkeypatch.setattr(cmd, "_start_existing_container", lambda: None)
    monkeypatch.setattr(cmd, "_create_container", lambda: None)
    monkeypatch.setattr(cmd, "_wait_for_localhost_http", lambda: False)
    monkeypatch.setattr(cmd, "_docker_capture", lambda _args: "Up 2 minutes")

    def _docker_inspect_json(template: str) -> dict[str, JsonValue] | None:
        if "Ports" in template:
            return {"6333/tcp": [], "6334/tcp": []}
        return {}

    monkeypatch.setattr(cmd, "_docker_inspect_json", _docker_inspect_json)

    caplog.set_level(logging.ERROR, logger="sec_nlp")

    with pytest.raises(RuntimeError, match="localhost:6333"):
        cmd.cli_cmd()

    message_text = caplog.text
    assert "localhost:6333 is still unreachable" in message_text
    assert "Attached networks" in message_text
    assert "runtime network endpoint is missing" in message_text


def test_qdrant_info_reports_stored_vectors_when_index_is_empty(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Collection info should show stored vectors even below indexing threshold."""
    cmd = QdrantInfo(collection_name="test_collection")
    info = _FakeCollectionInfo(
        status="green",
        vectors_count=None,
        points_count=294,
        indexed_vectors_count=0,
        config=_FakeCollectionConfig(
            params=_FakeCollectionParams(
                vectors=VectorParams(size=2560, distance=Distance.COSINE),
                on_disk_payload=False,
            ),
            optimizer_config=_FakeOptimizerConfig(
                deleted_threshold=0.2,
                indexing_threshold=10000,
            ),
        ),
    )

    monkeypatch.setattr(
        cmd, "_setup_qdrant_client", lambda: _FakeQdrantClient(info)
    )

    caplog.set_level(logging.INFO, logger="sec_nlp")

    cmd.cli_cmd()

    assert "Stored vectors: 294" in caplog.text
    assert "Points: 294" in caplog.text
    assert "Indexed vectors: 0" in caplog.text
