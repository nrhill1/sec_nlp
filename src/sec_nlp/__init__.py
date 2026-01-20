# src/sec_nlp/__init__.py
"""SEC NLP - CLI tool for SEC filing analysis."""

from importlib.metadata import (
    PackageNotFoundError,
    version as _pkg_version,
)

try:
    __version__ = _pkg_version("sec_nlp")
except PackageNotFoundError:
    __version__ = "<null>"

from .cli import main
from .core import (
    FilingMode,
    Loader,
    logger,
    setup_logging,
)
from .core.llm import (
    build_ollama_llm,
    build_runnable,
)
from .pipelines import (
    BasePipeline,
    BasePipelineResult,
    BasePipelineSettings,
)

__all__: tuple[str, ...] = (
    "__version__",
    # CLI
    "main",
    # Core
    "Loader",
    "FilingMode",
    "logger",
    "setup_logging",
    # LLM
    "build_ollama_llm",
    "build_runnable",
    # Pipelines
    "BasePipelineSettings",
    "BasePipeline",
    "BasePipelineResult",
)
