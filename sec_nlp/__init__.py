# sec_nlp/__init__.py
"""SEC NLP - CLI tool for SEC filing analysis."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("sec_nlp")
except PackageNotFoundError:
    __version__ = "0.0.0"


from sec_nlp.config import settings
from sec_nlp.core import FilingMode, Pipeline, Preprocessor, SECFilingDownloader
from sec_nlp.llm import FlanT5LocalLLM, LocalLLM, OllamaLLM
from sec_nlp.llm.chains import (
    SummarizationInput,
    SummarizationOutput,
    build_summarization_runnable,
)

__all__: list[str] = [
    "__version__",
    # Core
    "Pipeline",
    "SECFilingDownloader",
    "Preprocessor",
    "FilingMode",
    # LLM
    "LocalLLM",
    "FlanT5LocalLLM",
    "OllamaLLM",
    "SummarizationInput",
    "SummarizationOutput",
    "build_summarization_runnable",
    # Config
    "settings",
]
