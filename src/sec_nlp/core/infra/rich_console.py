# src/sec_nlp/core/infra/rich_console.py
"""Shared Rich console singleton, theme definition, and renderable helpers.

Defines the project-wide "digital green" color palette used by every Rich
console, styled logger output, CLI formatting helper, and pipeline progress
bar.  All semantic color tokens live in ``GLOBAL_RICH_THEME``; raw ANSI
escape strings are exposed via ``ANSI_PALETTE`` so that the logger module
can colorize without importing Rich.
"""

from __future__ import annotations

from rich.console import Console
from rich.theme import Theme

# ---------------------------------------------------------------------------
# Digital-green financial terminal palette
# ---------------------------------------------------------------------------
#   primary   #00d75f  (green3)          – headings, labels, active highlights
#   accent    #00ff87  (spring_green2)   – emphasis, strong highlights
#   secondary #87d7af  (dark_sea_green)  – softer badges, topic chips
#   muted     grey37                     – de-emphasis, metadata
#   dim_green #5f8787                    – timestamps, tz markers
#   warn      #ffaf00  (orange1)         – amber/gold financial warnings
#   error     #ff5f5f  (indian_red1)     – errors
#   critical  #ff005f                    – fatal / critical
#   info_blue #00d7ff  (deep_sky_blue1)  – informational contrast
# ---------------------------------------------------------------------------

GLOBAL_RICH_THEME: Theme = Theme(
    {
        # Semantic tokens used by CLI, interactive mode, and pipeline output
        "accent": "#00d75f",
        "accent_bold": "bold #00ff87",
        "title": "bold #00ff87",
        "good": "#00d75f",
        "warn": "#ffaf00",
        "error": "#ff5f5f",
        "muted": "grey37",
        "secondary": "#87d7af",
        # Logging tokens
        "log.time": "#5f8787",
        "log.tz": "#87d7af",
        "log.name": "#87d7af",
        "log.level.debug": "#5f8787",
        "log.level.info": "#00d75f",
        "log.level.warning": "#ffaf00",
        "log.level.error": "#ff5f5f",
        "log.level.critical": "bold #ff005f",
    }
)

# ---------------------------------------------------------------------------
# Raw ANSI palette for non-Rich output (logger ColoredFormatter, color_text)
# ---------------------------------------------------------------------------
ANSI_PALETTE: dict[str, str] = {
    "primary": "\033[38;2;0;215;95m",  # #00d75f  green3
    "accent": "\033[38;2;0;255;135m",  # #00ff87  spring_green2
    "secondary": "\033[38;2;135;215;175m",  # #87d7af  dark_sea_green
    "muted": "\033[38;2;78;78;78m",  # grey37
    "dim_green": "\033[38;2;95;135;135m",  # #5f8787
    "warn": "\033[38;2;255;175;0m",  # #ffaf00  orange1
    "error": "\033[38;2;255;95;95m",  # #ff5f5f  indian_red1
    "critical": "\033[38;2;255;0;95m",  # #ff005f
    "info_blue": "\033[38;2;0;215;255m",  # #00d7ff  deep_sky_blue1
    "reset": "\033[0m",
    "dim": "\033[2m",
    "bold": "\033[1m",
}

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
