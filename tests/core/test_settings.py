# tests/core/test_settings.py
"""Tests for storage settings independent of a source checkout."""

from pathlib import Path

from scripts.utils import find_project_root
from sec_nlp.core.infra.settings import CACHE_DIR, DATA_DIR


def test_installed_storage_paths_are_absolute() -> None:
    """Keep cache and data under resolved user locations."""
    assert CACHE_DIR.is_absolute()
    assert DATA_DIR.is_absolute()
    assert Path(__file__).resolve().parents[2] != CACHE_DIR


def test_developer_scripts_locate_checkout_separately() -> None:
    """Resolve developer checkout without coupling runtime storage to it."""
    assert (find_project_root() / "pyproject.toml").is_file()
