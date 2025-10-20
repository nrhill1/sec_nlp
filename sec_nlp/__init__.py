# sec_nlp/__init__.py
"""SEC NLP - CLI tool for SEC filing analysis."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("sec_nlp")
except PackageNotFoundError:
    __version__ = "0.0.0"

from sec_nlp.core import (
    FilingMode,
    Pipeline,
    Preprocessor,
    SECFilingDownloader,
    get_logger,
    settings,
    setup_logging,
)
from sec_nlp.core.llm import (
    FlanT5LocalLLM,
    LocalLLMBase,
    SummarizationInput,
    SummarizationOutput,
    build_ollama_llm,
    build_summarization_runnable,
)

__all__: list[str] = [
    "__version__",
    # Core
    "Pipeline",
    "SECFilingDownloader",
    "Preprocessor",
    "FilingMode",
    # Config
    "settings",
    "get_logger",
    "setup_logging",
    # LLM
    "LocalLLMBase",
    "FlanT5LocalLLM",
    "build_ollama_llm",
    "SummarizationInput",
    "SummarizationOutput",
    "build_summarization_runnable",
]
