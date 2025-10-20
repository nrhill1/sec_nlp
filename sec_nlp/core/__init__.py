# sec_nlp/core/__init__.py
"""Core functionality for SEC NLP."""

from sec_nlp.core.config import get_logger, settings, setup_logging
from sec_nlp.core.downloader import SECFilingDownloader
from sec_nlp.core.pipeline import Pipeline, default_prompt_path
from sec_nlp.core.preprocessor import Preprocessor
from sec_nlp.core.types import FilingMode

__all__: list[str] = [
    "FilingMode",
    "Pipeline",
    "default_prompt_path",
    "Preprocessor",
    "SECFilingDownloader",
    "get_logger",
    "settings",
    "setup_logging",
]
