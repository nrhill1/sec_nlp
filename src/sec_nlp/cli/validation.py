"""Specialized formatting utilities for CLI validation errors."""

from __future__ import annotations

import re

from pydantic import ValidationError
from pydantic_core import InitErrorDetails

from sec_nlp.cli.formatting import (
    format_divider,
    format_section_header,
)
from sec_nlp.core.infra.logger import color_text

# Type alias for validation error details from Pydantic
type ValidationErrorDetail = InitErrorDetails


def format_validation_error(error: ValidationError) -> str:
    """Format a pydantic validation error with helpful suggestions.

    Args:
        error: The validation error

    Returns:
        Formatted error message with suggestions
    """
    lines: list[str] = []

    # Header
    lines.append("")
    lines.append(
        format_section_header("Configuration Error", style="box", width=60)
    )
    lines.append("")

    # Group errors by field for better organization
    errors_by_field: dict[str, list[dict[str, str]]] = {}
    for err in error.errors():
        loc = ".".join(str(x) for x in err["loc"])
        if loc not in errors_by_field:
            errors_by_field[loc] = []
        err_dict = {"type": str(err["type"]), "msg": str(err["msg"])}
        errors_by_field[loc].append(err_dict)

    # Format each field's errors
    for field, field_errors in errors_by_field.items():
        lines.append(color_text(f"  {field}", color="yellow"))

        for err in field_errors:
            msg = err["msg"]
            err_type = err["type"]

            # Main error message
            lines.append(f"    {color_text('✗', color='red')} {msg}")

            # Add type-specific suggestions
            suggestion = _get_error_suggestion(field, err_type, msg)
            if suggestion:
                lines.append(
                    f"    {color_text('→', color='green')} {suggestion}"
                )

        lines.append("")

    # Footer with general help
    lines.append(format_divider(width=60))
    lines.append(
        f"  {color_text('Tip:', color='cyan')} "
        "Run 'sec-nlp <command> --help' for available options."
    )

    return "\n".join(lines)


def _get_error_suggestion(field: str, err_type: str, msg: str) -> str:
    """Get a helpful suggestion for a specific error type.

    Args:
        field: The field name
        err_type: The error type
        msg: The error message

    Returns:
        A suggestion string, or empty string if no suggestion applies
    """
    flag_name = f"--{field.replace('.', '-')}"

    if err_type == "missing":
        return f"This field is required. Add {flag_name} <value>"
    if err_type == "string_type":
        return "Expected a string value. Try quoting the value."
    if err_type == "int_parsing":
        return "Expected an integer (e.g., 5, 10, 100)"
    if err_type == "float_parsing":
        return "Expected a number (e.g., 0.5, 1.0)"
    if err_type == "greater_than_equal":
        match = re.search(r"greater than or equal to (\d+)", msg)
        if match:
            min_val = match.group(1)
            return f"Expected a value >= {min_val}"
    elif err_type == "less_than_equal":
        match = re.search(r"less than or equal to (\d+)", msg)
        if match:
            max_val = match.group(1)
            return f"Expected a value <= {max_val}"
    elif "enum" in err_type or "literal" in err_type:
        # Extract allowed values from message
        match = re.search(r"\[([^\]]+)\]", msg)
        if match:
            values_str = match.group(1)
            return f"Use one of: {values_str}"
    elif err_type == "date_parsing":
        return "Expected a date in YYYY-MM-DD format (e.g., 2024-01-15)"
    elif err_type == "url_type":
        return "Expected a valid URL starting with http:// or https://"
    elif err_type == "value_error":
        return f"Invalid value: {msg}"

    return ""


def format_unknown_arg_error(
    arg: str, suggestions: list[str] | None = None
) -> str:
    """Format an unknown argument error with suggestions.

    Args:
        arg: The unknown argument
        suggestions: Optional list of suggested similar arguments

    Returns:
        Formatted error message
    """
    lines: list[str] = []

    lines.append("")
    lines.append(
        format_section_header(f"Unknown Argument: {arg}", style="box", width=60)
    )
    lines.append("")

    if suggestions:
        lines.append("  Did you mean one of these?")
        lines.append("")
        for suggestion in suggestions[:3]:
            lines.append(f"    {color_text('→', color='cyan')} --{suggestion}")
        lines.append("")

    lines.append(format_divider(width=60))
    lines.append(
        f"  {color_text('Tip:', color='cyan')} "
        "Run 'sec-nlp <command> --help' for available options."
    )

    return "\n".join(lines)


def format_validation_summary(errors: list[ValidationErrorDetail]) -> str:
    """Create a compact summary of validation errors.

    Args:
        errors: List of validation error dicts

    Returns:
        Formatted summary string
    """
    lines: list[str] = []

    lines.append("")
    lines.append(
        format_section_header("Validation Issues", style="box", width=50)
    )
    lines.append("")

    for err in errors:
        loc_tuple = err.get("loc") if isinstance(err, dict) else ()
        loc = ".".join(str(x) for x in loc_tuple) if loc_tuple else "unknown"
        msg = str(err.get("msg", ""))
        lines.append(f"  {color_text(loc, color='yellow')}")
        lines.append(f"    {msg}")
        lines.append("")

    return "\n".join(lines)
