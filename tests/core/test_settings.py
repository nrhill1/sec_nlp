"""Tests for project settings and root discovery."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from sec_nlp.core.infra import settings
from sec_nlp.core.infra.settings import PathSecurityError


def test_project_root_matches_repository() -> None:
    """PROJECT_ROOT should match the repository root derived from this test file."""
    expected_root = Path(__file__).resolve().parents[2]
    assert expected_root == settings.PROJECT_ROOT
    assert (settings.PROJECT_ROOT / "pyproject.toml").is_file()


def test_project_metadata_valid() -> None:
    """pyproject.toml should declare the expected package name/version."""
    pyproject = settings.PROJECT_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    assert data.get("project", {}).get("name") == "sec-nlp"
    assert data.get("project", {}).get("version")


def test_project_root_from_module_uses_parent_traversal() -> None:
    """Deriving the root from a module path should land on the repo root."""
    module_file = settings.__file__
    assert module_file is not None
    derived = settings._project_root_from_module(Path(module_file))
    assert derived == Path(__file__).resolve().parents[2]


def test_validate_project_root_rejects_site_packages(tmp_path: Path) -> None:
    """Roots inside site-packages should be refused."""
    site_root = (
        tmp_path / "venv" / "lib" / "python" / "site-packages" / "sec-nlp"
    )
    site_root.mkdir(parents=True)
    (site_root / "pyproject.toml").write_text(
        '[project]\nname = "sec-nlp"\nversion = "0.0.0"\n',
        encoding="utf-8",
    )

    with pytest.raises(PathSecurityError):
        settings._validate_project_root(site_root)


def test_validate_project_root_rejects_wrong_name(tmp_path: Path) -> None:
    """Wrong project name should raise PathSecurityError."""
    wrong_root = tmp_path / "sec-nlp"
    wrong_root.mkdir(parents=True)
    (wrong_root / "pyproject.toml").write_text(
        '[project]\nname = "not-sec-nlp"\nversion = "0.0.0"\n',
        encoding="utf-8",
    )

    with pytest.raises(PathSecurityError):
        settings._validate_project_root(wrong_root)
