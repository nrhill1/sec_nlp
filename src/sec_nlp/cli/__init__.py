# src/sec_nlp/cli/__init__.py
# sec_nlp/cli/__init__.py
"""CLI entry point and command utilities."""

from .__main__ import main
from .command import BasePipelineCommand
from .formatting import (
    ColumnSpec,
    center_text,
    format_config_block,
    format_divider,
    format_key_value,
    format_section_header,
    format_status,
    format_table,
    get_terminal_width,
)
from .validation import (
    format_unknown_arg_error,
    format_validation_error,
    format_validation_summary,
)

__all__: tuple[str, ...] = (
    "main",
    "BasePipelineCommand",
    "ColumnSpec",
    "center_text",
    "format_config_block",
    "format_divider",
    "format_key_value",
    "format_section_header",
    "format_status",
    "format_table",
    "format_unknown_arg_error",
    "format_validation_error",
    "format_validation_summary",
    "get_terminal_width",
)
