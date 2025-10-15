from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path

try:
    __version__ = _pkg_version("sec_nlp")
except PackageNotFoundError:
    __version__ = "0.0.0"

from .types import FilingMode
from .pipelines import Pipeline
from .chains import (
    SummaryPayload,
    SummarizationInput,
    SummarizationOutput,
    SummarizationResult,
    build_sec_runnable,
)
from .llms import LocalLLM, FlanT5LocalLLM
from .utils import SECFilingDownloader, Preprocessor
from .cli.__main__ import main as cli_main


__all__ = [
    "__version__",
    "FilingMode",
    "Pipeline",
    "SummaryPayload",
    "build_sec_runnable",
    "LocalLLM",
    "FlanT5LocalLLM",
    "SummarizationInput",
    "SummarizationOutput",
    "SummarizationResult",
    "SECFilingDownloader",
    "Preprocessor",
    "cli_main",
]
