# tests/pipelines/conftest.py
"""Isolate specialist execution bookkeeping from installed user data.

Each test receives its own SQLite registry so execution tests can assert stable
run identifiers without writing into a developer's application cache.
"""

from pathlib import Path

import pytest

from sec_nlp.pipelines.observability import run_registry


@pytest.fixture(autouse=True)
def isolated_run_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Route lazily created run registries into the test temporary directory."""
    monkeypatch.setattr(
        run_registry, "DEFAULT_REGISTRY_PATH", tmp_path / "runs.db"
    )
    monkeypatch.setattr(run_registry, "_registry", None)
