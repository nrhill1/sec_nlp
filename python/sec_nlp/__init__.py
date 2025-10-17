from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("sec_nlp")
except PackageNotFoundError:
    __version__ = "0.0.0"

from .chains import (
    SummarizationInput,
    SummarizationOutput,
    SummarizationResult,
    SummaryPayload,
    build_sec_runnable,
)
from .cli.__main__ import main as cli_main
from .llms import FlanT5LocalLLM, LocalLLM
from .pipelines import Pipeline
from .types import FilingMode
from .utils import Preprocessor, SECFilingDownloader

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
