# sec_nlp/cli/__init__.py
"""CLI entry point and command utilities."""

from .__main__ import main
from .command import PipelineCommand

__all__: tuple[str, ...] = (
    "main",
    "PipelineCommand",
)
