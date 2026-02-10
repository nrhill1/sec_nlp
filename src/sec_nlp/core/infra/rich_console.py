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

# ---------------------------------------------------------------------------
# Singleton Console (stderr) — all pipeline / logger output goes through this
# so that Rich can coordinate live displays (Progress, Status) with logging.
# ---------------------------------------------------------------------------
_CONSOLE: Console | None = None


def get_rich_console() -> Console:
    """Return the shared Rich console singleton (stderr, themed).

    Every caller that writes directly to the terminal should use this so that
    Rich Progress / Status bars are not corrupted by interleaved output.
    """
    global _CONSOLE  # noqa: PLW0603
    if _CONSOLE is None:
        _CONSOLE = Console(
            theme=GLOBAL_RICH_THEME,
            soft_wrap=True,
            color_system="truecolor",
            stderr=True,
        )
    return _CONSOLE


def create_rich_console(
    *,
    force_terminal: bool | None = None,
    width: int | None = None,
    stderr: bool = True,
    no_color: bool | None = None,
) -> Console:
    """Create a **new** Rich console with custom parameters.

    Use this instead of ``get_rich_console()`` when you need a separate
    instance — e.g. for string capture (``console.capture()``) or for
    writing to stdout instead of stderr.
    """
    return Console(
        theme=GLOBAL_RICH_THEME,
        force_terminal=force_terminal,
        width=width,
        soft_wrap=True,
        color_system="truecolor",
        stderr=stderr,
        no_color=no_color,
    )
