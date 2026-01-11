# src/sec_nlp/cli/formatting.py
"""CLI output formatting utilities for consistent terminal display."""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sec_nlp.core.infra.logger import color_text, visible_length


@dataclass(frozen=True)
class ColumnSpec:
    """Column specification for table rendering."""

    header: str
    align: Literal["left", "right", "center"] = "left"
    min_width: int | None = None
    max_width: int | None = None
    color: str | None = None


def get_terminal_width(default: int = 80) -> int:
    """Get current terminal width."""
    return shutil.get_terminal_size((default, 20)).columns


def center_text(text: str, width: int | None = None) -> str:
    """Center text within a given width, accounting for ANSI codes."""
    term_width = width if width is not None else get_terminal_width()
    text_width = visible_length(text)
    padding = max((term_width - text_width) // 2, 0)
    return " " * padding + text


def format_section_header(
    title: str,
    *,
    subtitle: str | None = None,
    width: int | None = None,
    style: Literal["box", "line", "minimal"] = "box",
    color: str = "cyan",
) -> str:
    """Create a styled section header for CLI output.

    Args:
        title: Main header title
        subtitle: Optional subtitle below title
        width: Box width (defaults to terminal width)
        style: Header style - 'box' (bordered), 'line' (underlined), 'minimal'
        color: Color for the header

    Returns:
        Formatted header string
    """
    term_width = width if width is not None else get_terminal_width()

    if style == "minimal":
        header = color_text(f"  {title}  ", color=color)
        if subtitle:
            header += "\n" + color_text(f"  {subtitle}  ", color="dim")
        return "\n" + center_text(header, term_width) + "\n"

    if style == "line":
        title_line = color_text(f"  {title}  ", color=color)
        line_width = max(visible_length(title_line), 40)
        divider = color_text("─" * line_width, color="dim")
        lines = [
            "",
            center_text(title_line, term_width),
            center_text(divider, term_width),
        ]
        if subtitle:
            sub_line = color_text(f"  {subtitle}  ", color="dim")
            lines.append(center_text(sub_line, term_width))
        lines.append("")
        return "\n".join(lines)

    # Box style (default)
    visible_title = visible_length(title)
    visible_sub = visible_length(subtitle) if subtitle else 0
    inner_width = max(visible_title, visible_sub, 30)
    box_width = min(inner_width + 6, term_width - 4)

    top = f"╔{'═' * (box_width - 2)}╗"
    bottom = f"╚{'═' * (box_width - 2)}╝"
    title_padded = title.center(box_width - 4)
    mid = f"║ {title_padded} ║"

    lines = ["", top, mid]
    if subtitle:
        sub_padded = subtitle.center(box_width - 4)
        lines.append(f"║ {sub_padded} ║")
    lines.append(bottom)
    lines.append("")

    colored_lines = [color_text(line, color=color) for line in lines]
    return "\n".join(center_text(line, term_width) for line in colored_lines)


def format_divider(
    char: str = "─",
    length: int | None = None,
    color: str = "dim",
    centered: bool = True,
) -> str:
    """Create a horizontal divider line.

    Args:
        char: Character to repeat
        length: Line length (defaults to 60 or terminal width)
        color: Divider color
        centered: Whether to center the divider

    Returns:
        Formatted divider string
    """
    line_length = (
        length if length is not None else min(60, get_terminal_width() - 4)
    )
    divider = color_text(char * line_length, color=color)
    if centered:
        return center_text(divider)
    return divider


def format_key_value(
    label: str,
    value: str | None,
    *,
    label_width: int = 15,
    icon: str = "➜",
    label_color: str = "blue",
    value_color: str | None = None,
) -> str:
    """Format a key-value pair for display.

    Args:
        label: The key/label
        value: The value (None shows as "—")
        label_width: Fixed width for label alignment
        icon: Icon to prefix the label
        label_color: Color for the label
        value_color: Optional color for the value

    Returns:
        Formatted key-value string
    """
    display_value = value if value is not None else "—"
    label_part = f"{icon} {label}:".ljust(label_width + 3)
    colored_label = color_text(label_part, color=label_color)
    if value_color:
        display_value = color_text(display_value, color=value_color)
    return f"{colored_label} {display_value}"


def format_table(
    rows: Sequence[Sequence[str]],
    *,
    headers: Sequence[str] | None = None,
    column_specs: Sequence[ColumnSpec] | None = None,
    border: bool = True,
    centered: bool = True,
    header_color: str = "cyan",
    row_colors: list[str] | None = None,
) -> str:
    """Format data as an aligned table.

    Args:
        rows: Table rows (each row is a sequence of cell values)
        headers: Optional column headers
        column_specs: Optional detailed column specifications
        border: Whether to show border characters
        centered: Whether to center the table in terminal
        header_color: Color for header row
        row_colors: Optional per-column colors for data rows

    Returns:
        Formatted table string
    """
    if not rows and not headers:
        return ""

    # Determine column count
    num_cols = len(headers) if headers else len(rows[0]) if rows else 0
    if num_cols == 0:
        return ""

    # Calculate column widths
    widths: list[int] = []
    for col_idx in range(num_cols):
        col_values = [
            str(row[col_idx]) if col_idx < len(row) else "" for row in rows
        ]
        if headers and col_idx < len(headers):
            col_values.append(headers[col_idx])

        max_width = (
            max(visible_length(v) for v in col_values) if col_values else 0
        )

        # Apply column spec constraints if provided
        if column_specs and col_idx < len(column_specs):
            spec = column_specs[col_idx]
            if spec.min_width is not None:
                max_width = max(max_width, spec.min_width)
            if spec.max_width is not None:
                max_width = min(max_width, spec.max_width)

        widths.append(max_width)

    def _align_cell(
        text: str, width: int, align: str, color: str | None = None
    ) -> str:
        # Get visible length (ignoring ANSI codes already in text)
        text_len = visible_length(text)
        padding = width - text_len
        if padding <= 0:
            padded = text
        elif align == "right":
            padded = " " * padding + text
        elif align == "center":
            left_pad = padding // 2
            right_pad = padding - left_pad
            padded = " " * left_pad + text + " " * right_pad
        else:  # left
            padded = text + " " * padding

        # Apply color to the content portion only, preserving padding spaces
        if color and padding > 0:
            if align == "right":
                return " " * padding + color_text(text, color=color)
            elif align == "center":
                left_pad = padding // 2
                right_pad = padding - left_pad
                return (
                    " " * left_pad
                    + color_text(text, color=color)
                    + " " * right_pad
                )
            else:  # left
                return color_text(text, color=color) + " " * padding
        elif color:
            return color_text(text, color=color)
        return padded

    def _get_align(col_idx: int) -> str:
        if column_specs and col_idx < len(column_specs):
            return column_specs[col_idx].align
        return "left"

    def _get_color(col_idx: int, is_header: bool) -> str | None:
        if is_header:
            return header_color
        if column_specs and col_idx < len(column_specs):
            return column_specs[col_idx].color
        if row_colors and col_idx < len(row_colors):
            return row_colors[col_idx]
        return None

    # Build table lines
    lines: list[str] = []
    sep = " │ " if border else "  "

    # Header row
    if headers:
        header_cells = [
            _align_cell(
                headers[i] if i < len(headers) else "",
                widths[i],
                _get_align(i),
                header_color,
            )
            for i in range(num_cols)
        ]
        lines.append(sep.join(header_cells))

        # Header divider
        if border:
            divider_parts = [
                color_text("─" * widths[i], color="dim")
                for i in range(num_cols)
            ]
            lines.append(color_text("─┼─", color="dim").join(divider_parts))
        else:
            divider_parts = ["─" * widths[i] for i in range(num_cols)]
            lines.append(color_text("──".join(divider_parts), color="dim"))

    # Data rows
    for row in rows:
        cells = [
            _align_cell(
                str(row[i]) if i < len(row) else "",
                widths[i],
                _get_align(i),
                _get_color(i, is_header=False),
            )
            for i in range(num_cols)
        ]
        lines.append(sep.join(cells))

    table_text = "\n".join(lines)

    if centered:
        term_width = get_terminal_width()
        return "\n".join(center_text(line, term_width) for line in lines)

    return table_text


def format_config_block(
    items: Sequence[tuple[str, str | None]],
    *,
    title: str | None = None,
    centered: bool = True,
    icon: str = "➜",
) -> str:
    """Format a configuration block with aligned key-value pairs.

    Args:
        items: Sequence of (label, value) tuples
        title: Optional title for the block
        centered: Whether to center the block
        icon: Icon for each item

    Returns:
        Formatted config block string
    """
    if not items:
        return ""

    # Calculate label width for alignment
    label_width = max(len(label) for label, _ in items)

    lines: list[str] = []
    if title:
        lines.append(color_text(f"  {title}  ", color="cyan"))
        lines.append(color_text("─" * (label_width + 20), color="dim"))

    for label, value in items:
        lines.append(
            format_key_value(label, value, label_width=label_width, icon=icon)
        )

    if centered:
        term_width = get_terminal_width()
        return "\n".join(center_text(line, term_width) for line in lines)

    return "\n".join(lines)


def format_status(
    message: str,
    *,
    status: Literal["success", "error", "warning", "info"] = "info",
) -> str:
    """Format a status message with appropriate icon and color.

    Args:
        message: Status message text
        status: Status type

    Returns:
        Formatted status string
    """
    icons = {
        "success": "✓",
        "error": "✗",
        "warning": "⚠",
        "info": "ℹ",
    }
    colors = {
        "success": "green",
        "error": "red",
        "warning": "yellow",
        "info": "cyan",
    }
    icon = icons.get(status, "•")
    c = colors.get(status, "dim")
    return color_text(f"{icon} {message}", color=c)
