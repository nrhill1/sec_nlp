# sec_nlp/core/__init__.py
"""Core functionality for SEC NLP."""

from sec_nlp.core.config import get_logger, settings, setup_logging
from sec_nlp.core.downloader import FilingManager
from sec_nlp.core.enums import FilingMode
from sec_nlp.core.pipeline import Pipeline, default_prompt_path
from sec_nlp.core.preprocessor import Preprocessor

__all__: list[str] = [
    "FilingMode",
    "Pipeline",
    "default_prompt_path",
    "Preprocessor",
    "FilingManager",
    "get_logger",
    "settings",
    "setup_logging",
]
