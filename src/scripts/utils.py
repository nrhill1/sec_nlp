# src/scripts/utils.py
"""Secure path utilities for scripts without using parent directory imports."""

import sys
import tomllib
from pathlib import Path

from sec_nlp.core.infra.settings import PROJECT_ROOT as _PROJECT_ROOT


def find_project_root() -> Path:
    """
    Return the validated project root discovered at import time.
    """
    return _PROJECT_ROOT


def get_src_path() -> Path:
    """
    Get the src directory path.

    Returns:
        Path to the src directory
    """
    return find_project_root() / "src"


def setup_import_path() -> None:
    """
    Add src directory to Python path if not already present.

    This allows importing sec_nlp modules from scripts without
    using relative imports or parent directory references.
    """
    src_path = str(get_src_path())

    # Only add if not already in path
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def get_project_info() -> dict[str, str]:
    """
    Read project information from pyproject.toml.

    Returns:
        Dictionary with project metadata
    """
    root = find_project_root()
    pyproject_path = root / "pyproject.toml"

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    project = data.get("project", {})
    return {
        "name": project.get("name", ""),
        "version": project.get("version", ""),
        "description": project.get("description", ""),
    }


# Module-level convenience functions
_PROJECT_ROOT_CACHE: Path | None = None
_SRC_PATH_CACHE: Path | None = None


def get_cached_project_root() -> Path:
    """Get project root with caching."""
    global _PROJECT_ROOT_CACHE
    if _PROJECT_ROOT_CACHE is None:
        _PROJECT_ROOT_CACHE = find_project_root()
    return _PROJECT_ROOT_CACHE


def get_cached_src_path() -> Path:
    """Get src path with caching."""
    global _SRC_PATH_CACHE
    if _SRC_PATH_CACHE is None:
        _SRC_PATH_CACHE = get_src_path()
    return _SRC_PATH_CACHE
