# src/sec_nlp/cli/commands/version.py
from importlib.metadata import PackageNotFoundError, version

from pydantic import BaseModel, ConfigDict

from sec_nlp.core.infra.logger import color_text, styled_header
from sec_nlp.core.infra.settings import PROJECT_ROOT


def _get_version() -> str:
    """Get version from package metadata or pyproject.toml."""
    # First try installed package metadata
    try:
        return version("sec-nlp")
    except PackageNotFoundError:
        pass

    # Fall back to pyproject.toml in development
    try:
        import tomllib

        pyproject_path = PROJECT_ROOT / "pyproject.toml"
        if pyproject_path.exists():
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                if pkg_version := data.get("project", {}).get("version"):
                    return str(pkg_version)
    except Exception:
        pass

    return "unknown"


class Version(BaseModel):
    """CLI command model for printing the installed sec-nlp version."""

    model_config = ConfigDict(defer_build=True)

    def cli_cmd(self) -> None:
        """Show version information."""
        version = _get_version()

        print(styled_header("SEC NLP"))
        print(color_text(f"Version: {version}", color="cyan"))
        print(
            color_text(
                "\nA high-performance CLI tool for SEC filings analysis",
                color="dim",
            )
        )
