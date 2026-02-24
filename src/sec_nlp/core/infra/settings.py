# src/sec_nlp/core/infra/settings.py
"""Project-level settings and root discovery."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path


class PathSecurityError(RuntimeError):
    """Raised when a path cannot be validated as safe."""


def _project_root_from_module(module_file: Path) -> Path:
    """Compute the project root based on the module location."""
    module_dir = module_file.parent.resolve()
    if "site-packages" in module_dir.parts:
        raise PathSecurityError(
            f"Project root cannot be inside site-packages: {module_dir}"
        )

    last_error: PathSecurityError | None = None
    for candidate in (module_dir, *module_dir.parents):
        try:
            return _validate_project_root(candidate)
        except PathSecurityError as exc:
            last_error = exc

    detail = f": {last_error}" if last_error else ""
    raise PathSecurityError(
        f"Failed to find project root from module file {module_file}{detail}"
    )


def _validate_project_root(root: Path) -> Path:
    """Validate pyproject.toml name/version and site-packages exclusion."""
    if any(part == "site-packages" for part in root.resolve().parts):
        raise PathSecurityError(
            f"Project root cannot be inside site-packages: {root}"
        )

    pyproject_path = root / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PathSecurityError(
            f"Failed to read pyproject.toml at {pyproject_path}: {exc}"
        ) from exc

    project = data.get("project", {})
    name = project.get("name")
    version = project.get("version")

    if name != "sec-nlp" or version is None:
        raise PathSecurityError(
            f"Invalid project root {root}: name={name} version={version}"
        )

    return root.resolve()


PROJECT_ROOT: Path = _validate_project_root(
    _project_root_from_module(Path(__file__))
)


def _read_int_setting(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise PathSecurityError(
            f"Invalid integer for {name}: {raw_value}"
        ) from exc


def _read_float_setting(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise PathSecurityError(
            f"Invalid float for {name}: {raw_value}"
        ) from exc


MARKET_CACHE_TTL_SECONDS: float = _read_float_setting(
    "SEC_NLP_MARKET_CACHE_TTL_SECONDS",
    300.0,
)
MARKET_CACHE_MAX_ENTRIES: int = _read_int_setting(
    "SEC_NLP_MARKET_CACHE_MAX_ENTRIES",
    128,
)
MARKET_RETRY_ATTEMPTS: int = _read_int_setting(
    "SEC_NLP_MARKET_RETRY_ATTEMPTS",
    3,
)
MARKET_RETRY_BACKOFF_SECONDS: float = _read_float_setting(
    "SEC_NLP_MARKET_RETRY_BACKOFF_SECONDS",
    0.5,
)
MARKET_RETRY_BACKOFF_MULTIPLIER: float = _read_float_setting(
    "SEC_NLP_MARKET_RETRY_BACKOFF_MULTIPLIER",
    2.0,
)
