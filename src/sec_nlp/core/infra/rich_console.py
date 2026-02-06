# src/sec_nlp/core/infra/rich_console.py
"""Shared Rich console helpers and theme."""

from __future__ import annotations

from rich.console import Console
from rich.theme import Theme

GLOBAL_RICH_THEME: Theme = Theme(
    {
        "accent": "bright_cyan",
        "accent_bold": "bold bright_cyan",
        "title": "bold white",
        "good": "green",
        "warn": "yellow",
        "error": "red",
        "muted": "grey62",
        "log.time": "grey62",
        "log.tz": "bright_magenta",
        "log.name": "magenta",
        "log.level.debug": "cyan",
        "log.level.info": "green",
        "log.level.warning": "yellow",
        "log.level.error": "red",
        "log.level.critical": "bold red",
    }
)


def get_rich_console(
    *,
    force_terminal: bool | None = None,
    width: int | None = None,
    stderr: bool = True,
    no_color: bool | None = None,
) -> Console:
    """Build a Rich console configured with the global theme."""
    return Console(
        theme=GLOBAL_RICH_THEME,
        force_terminal=force_terminal,
        width=width,
        soft_wrap=True,
        color_system="truecolor",
        stderr=stderr,
        no_color=no_color,
    )
