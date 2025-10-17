# ==============================================================================
# sec_nlp/__init__.py
# ==============================================================================
"""SEC NLP - CLI tool for SEC filing analysis."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("sec_nlp")
except PackageNotFoundError:
    __version__ = "0.0.0"

from sec_nlp.cli import main as cli_main
from sec_nlp.pipelines import Pipeline
from sec_nlp.pipelines.utils import FilingMode, Preprocessor, SECFilingDownloader
from sec_nlp.pipelines.utils.chains import (
    SummarizationInput,
    SummarizationOutput,
    SummarizationResult,
    SummaryPayload,
    build_sec_runnable,
)
from sec_nlp.pipelines.utils.llms import FlanT5LocalLLM, LocalLLM

__all__: list[str] = [
    "__version__",
    "cli_main",
    "Pipeline",
    "FilingMode",
    "SECFilingDownloader",
    "Preprocessor",
    "LocalLLM",
    "FlanT5LocalLLM",
    "SummarizationInput",
    "SummarizationOutput",
    "SummarizationResult",
    "SummaryPayload",
    "build_sec_runnable",
]
