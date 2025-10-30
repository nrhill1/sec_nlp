# src/sec_nlp/cli/commands/__init__.py
from .analyze import analyze_command
from .embed import embed_command
from .examples import examples_command
from .info import info_command
from .summarize import summarize_command
from .version import version_command

__all__ = [
    "summarize_command",
    "analyze_command",
    "embed_command",
    "info_command",
    "examples_command",
    "version_command",
]
