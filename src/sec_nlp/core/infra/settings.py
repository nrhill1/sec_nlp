"""Project-level settings and root discovery."""

from __future__ import annotations

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
