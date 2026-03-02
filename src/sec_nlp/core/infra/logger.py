# src/sec_nlp/core/infra/logger.py
"""Centralized logging configuration, formatters, and styled output helpers.

Provides ``setup_logging()`` for one-time application-wide log setup with
console and file handlers, colored and Rich-aware formatters, and a suite
of styled output helpers (dividers, headers, badges, bullets) used by CLI
commands and pipeline progress reporting.
"""

import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Literal, TextIO

from rich.text import Text
from rich.traceback import Traceback
from tqdm import tqdm

from sec_nlp.core.infra.rich_console import (
    ANSI_PALETTE,
    create_rich_console,
    get_rich_console,
)


class TqdmLoggingHandler(logging.StreamHandler[TextIO]):
    """Log handler that routes output through ``tqdm.write`` to avoid clobbering progress bars."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            if tqdm is None:
                self.stream.write(f"{msg}{self.terminator}")
            else:
                tqdm.write(msg, file=self.stream)
            self.flush()
        except Exception:
            self.handleError(record)


_logging_configured: bool = False


class ColoredFormatter(logging.Formatter):
    """ANSI color and icon formatter for human-readable console log output."""

    COLORS: dict[str, str] = {
        "DEBUG": ANSI_PALETTE["dim_green"],
        "INFO": ANSI_PALETTE["primary"],
        "WARNING": ANSI_PALETTE["warn"],
        "ERROR": ANSI_PALETTE["error"],
        "CRITICAL": ANSI_PALETTE["critical"],
    }
    TIME_COLOR: str = ANSI_PALETTE["dim_green"]
    TZ_OFFSET_COLOR: str = ANSI_PALETTE["dim_green"]
    TZ_NAME_COLOR: str = ANSI_PALETTE["secondary"]
    ICONS: dict[str, str] = {
        "DEBUG": "●",
        "INFO": "▸",
        "WARNING": "▲",
        "ERROR": "✖",
        "CRITICAL": "◆",
    }
    RESET: str = ANSI_PALETTE["reset"]

    def format(self, record: logging.LogRecord) -> str:
        """Add color and icon to log level."""
        levelname = record.levelname
        icon = self.ICONS.get(levelname, "•")
        padded = f"{icon} {levelname:<8}"
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{padded}{self.RESET}"
        else:
            record.levelname = padded
        return super().format(record)

    def formatTime(
        self, record: logging.LogRecord, datefmt: str | None = None
    ) -> str:
        """Colorize the timestamp with distinct timezone styling."""
        dt = datetime.fromtimestamp(record.created).astimezone()
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        offset = dt.strftime("%z")
        tz_name = dt.tzname() or ""

        result = f"{self.TIME_COLOR}{time_str}{self.RESET}"
        if offset:
            result += f" {self.TZ_OFFSET_COLOR}{offset}{self.RESET}"
        if tz_name:
            result += f" {self.TZ_NAME_COLOR}{tz_name}{self.RESET}"
        return result


class PaddedFormatter(logging.Formatter):
    """Plain formatter that strips trailing newlines for clean log output."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        return base.rstrip("\n")


class PaddedColoredFormatter(ColoredFormatter):
    """Colored formatter that strips trailing newlines for clean log output."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        return base.rstrip("\n")


class FileSafeFormatter(logging.Formatter):
    """Formatter that strips ANSI codes and non-ASCII characters for file logs."""

    def format(self, record: logging.LogRecord):
        base = super().format(record)
        return _sanitize_for_file(base)


class RichLogFormatter(logging.Formatter):
    """Rich-aware log formatter rendering styled text, timestamps, and tracebacks."""

    def __init__(
        self,
        *,
        show_time: bool,
        show_name: bool,
        datefmt: str | None = None,
    ) -> None:
        """Construct a Rich log formatter with configurable timestamp and name display."""
        super().__init__(datefmt=datefmt)
        self._console = create_rich_console(stderr=True)
        self._show_time = show_time
        self._show_name = show_name

    def format(self, record: logging.LogRecord) -> str:
        message_text = Text.from_ansi(record.getMessage())
        parts: list[Text] = []

        if self._show_time:
            dt = datetime.fromtimestamp(record.created).astimezone()
            timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
            offset = dt.strftime("%z")
            tzname = dt.tzname() or "local"
            time_block = Text(timestamp, style="log.time")
            if offset:
                time_block.append(f" {offset}", style="muted")
            if tzname:
                time_block.append(f" {tzname}", style="log.tz")
            parts.append(time_block)

        level_style = f"log.level.{record.levelname.lower()}"
        parts.append(Text(record.levelname, style=level_style))

        if self._show_name:
            parts.append(Text(record.name, style="log.name"))

        separator = Text(" - ", style="muted")
        is_multiline = "\n" in message_text.plain
        line = Text()
        for idx, part in enumerate(parts):
            if idx:
                line.append(separator)
            line.append(part)

        renderables = []
        if is_multiline:
            if line:
                renderables.append(line)
            renderables.append(message_text)
        else:
            if line:
                line.append(separator)
            line.append(message_text)
            renderables.append(line)
        exc_info = record.exc_info
        if exc_info:
            exc_type, exc, tb = exc_info
            if exc_type is not None and exc is not None and tb is not None:
                renderables.append(
                    Traceback.from_exception(
                        exc_type,
                        exc,
                        tb,
                        show_locals=False,
                        width=self._console.width or 120,
                    )
                )
            elif exc is not None:
                renderables.append(Text(str(exc), style="log.level.error"))
        elif record.stack_info:
            renderables.append(Text.from_ansi(record.stack_info))

        with self._console.capture() as capture:
            for renderable in renderables:
                self._console.print(renderable, highlight=False)
        return capture.get().rstrip("\n")


def get_timestamped_log_path(
    prefix: str = "run_log", ext: str = ".log"
) -> Path:
    """
    Generate a timestamped log file path.

    Args:
        prefix: Filename prefix
        ext: File extension (default: .log)

    Returns:
        Path object for timestamped log file

    Usage:
        log_path = get_timestamped_log_path("pipeline")
        # Returns: logs/pipeline_20250105T143022-0500.log
    """
    now = datetime.now().astimezone()
    timestamp = now.strftime("%Y%m%dT%H%M%S%Z")
    return Path(f"./logs/{prefix}_{timestamp}{ext}")


def setup_logging(
    level: str | int = "INFO",
    format_type: Literal["simple", "detailed", "json"] = "detailed",
    log_file: Path | str | None = None,
    enable_colors: bool = True,
) -> logging.Logger:
    """
    Configure application-wide logging.

    This should be called once at application startup, typically in your
    CLI entrypoint or main() function.

    Args:
        level: Console log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) or int.
            File logging always captures DEBUG.
        format_type: Log format style
        log_file: Optional file path to write logs to
        enable_colors: Enable colored output for console (ignored if log_file or json format)

    Returns:
        The configured global logger

    Usage:
        # Simple setup with defaults
        setup_logging()

        # Custom setup
        setup_logging(level="DEBUG", format_type="detailed")

        # With file output
        setup_logging(log_file="logs/app.log")
    """
    global _logging_configured

    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    formats: dict[str, str] = {
        "simple": "%(levelname)s - %(message)s",
        "detailed": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "json": '{"time":"%(asctime)s","name":"%(name)s","level":"%(levelname)s","message":"%(message)s"}',
    }

    log_format = formats.get(format_type, formats["simple"])
    date_format = "%Y-%m-%d %H:%M:%S %z"

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # always capture full detail internally
    root_logger.handlers.clear()

    # Console handler — use a custom StreamHandler that writes to the Rich Console
    # so that output automatically coordinates with any active Rich live displays
    # (Progress, Status) instead of clobbering them. This is a key fix: writing
    # directly to stderr bypasses Rich's coordination; console.print() respects it.
    console_handler: logging.Handler
    use_colors = enable_colors and format_type != "json"
    if use_colors:
        console_formatter = PaddedColoredFormatter(
            log_format, datefmt=date_format
        )
    else:
        console_formatter = PaddedFormatter(log_format, datefmt=date_format)

    # Create a custom handler that writes via get_rich_console() to coordinate
    # with live displays, but preserves the ColoredFormatter for readability.
    class RichConsoleStreamHandler(logging.Handler):
        """Stream handler that emits via Rich console for coordination."""

        def emit(self, record: logging.LogRecord) -> None:
            try:
                msg = self.format(record)
                get_rich_console().print(msg, highlight=False)
            except Exception:
                self.handleError(record)

    console_handler = RichConsoleStreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(level)
    # Suppress noisy third-party warning spam from console while keeping it in file logs
    console_handler.addFilter(
        lambda record: not str(record.name).startswith(
            "langchain_core.prompts.loading"
        )
    )
    # Collapse repeated unstructured warnings to keep console output readable
    unstructured_seen: set[str] = set()

    def _dedupe_unstructured_profiles(record: logging.LogRecord) -> bool:
        """Deduplicate unstructured profile entries while preserving order."""
        if not str(record.name).startswith("unstructured"):
            return True
        message = record.getMessage()
        if message != "Need to load profiles.":
            return True
        if message in unstructured_seen:
            return False
        unstructured_seen.add(message)
        return True

    console_handler.addFilter(_dedupe_unstructured_profiles)
    root_logger.addHandler(console_handler)

    # File handler
    log_file = log_file or get_timestamped_log_path()
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(
        log_path, encoding="ascii", errors="ignore"
    )
    file_handler.setLevel("DEBUG")
    file_formatter = FileSafeFormatter(log_format, datefmt=date_format)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Align package logger with root level and propagate (avoid double DEBUG on console)
    pkg_logger = logging.getLogger("sec_nlp")
    pkg_logger.handlers.clear()
    pkg_logger.setLevel(logging.DEBUG)
    pkg_logger.propagate = True

    # Announce log destination
    startup_msg = (
        f"Logging initialized -> root=DEBUG console={logging.getLevelName(level)} "
        f"format={format_type} file={log_path}"
    )
    root_logger.info(startup_msg)

    # Suppress noisy third-party loggers
    for lib in ["urllib3", "requests", "transformers", "torch", "httpx"]:
        logging.getLogger(lib).setLevel(logging.WARNING)
    logging.getLogger("unstructured").setLevel(logging.WARNING)

    root_logger.debug(
        "Logging configured: level=%s, format=%s, file=%s",
        logging.getLevelName(level),
        format_type,
        log_file or "console only",
    )
    return root_logger


class LogContext:
    """Context manager that temporarily overrides a logger's level and restores it on exit."""

    def __init__(self, logger: logging.Logger | str, level: str | int):
        """
        Args:
            logger: Logger instance or name
            level: Temporary log level
        """
        if isinstance(logger, str):
            logger = logging.getLogger(logger)
        self.logger = logger
        self.level = (
            level
            if isinstance(level, int)
            else getattr(logging, level.upper(), logging.INFO)
        )
        self.original_level = logger.level

    def __enter__(self) -> logging.Logger:
        """Set temporary log level."""
        self.logger.setLevel(self.level)
        return self.logger

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Restore original log level."""
        exc_type = type(exc) if exc is not None else exc_type
        if exc_type is not None and tb is not None:
            self.logger.debug(
                "Restoring log level after %s",
                exc_type.__name__,
            )
        self.logger.setLevel(self.original_level)


# Global logger instance
logger: logging.Logger = logging.getLogger("sec_nlp")

# Set up basic configuration at import time (will be reconfigured by setup_logging)
logger.setLevel(logging.DEBUG)
logger.propagate = True


def color_text(text: str, *, color: str) -> str:
    """Wrap text with ANSI color codes if supported."""
    colors: dict[str, str] = {
        "red": ANSI_PALETTE["error"],
        "green": ANSI_PALETTE["primary"],
        "yellow": ANSI_PALETTE["warn"],
        "blue": ANSI_PALETTE["secondary"],
        "magenta": ANSI_PALETTE["accent"],
        "cyan": ANSI_PALETTE["primary"],
        "dim": ANSI_PALETTE["dim"],
        "bold": ANSI_PALETTE["bold"],
    }
    reset: str = ANSI_PALETTE["reset"]
    if color not in colors:
        return text
    return f"{colors[color]}{text}{reset}"


_ANSI_RE: re.Pattern[str] = re.compile(r"\x1b\[[0-9;]*m")
_UNICODE_TRANSLATIONS = {
    ord("╔"): "+",
    ord("╗"): "+",
    ord("╚"): "+",
    ord("╝"): "+",
    ord("║"): "|",
    ord("═"): "-",
    ord("─"): "-",
    ord("•"): "*",
    ord("▸"): ">",
    ord("●"): "*",
    ord("▲"): "WARN",
    ord("✖"): "ERR",
    ord("◆"): "FAIL",
    ord("✓"): "OK",
    ord("✗"): "ERR",
}


def _sanitize_for_file(text):
    """Remove ANSI and control characters from file log output."""
    cleaned = _ANSI_RE.sub("", text)
    cleaned = cleaned.translate(_UNICODE_TRANSLATIONS)
    return cleaned.encode("ascii", "ignore").decode()


def _visible_len(text: str) -> int:
    """Length without ANSI escape codes."""
    return len(_ANSI_RE.sub("", text))


def visible_length(text: str) -> int:
    """Public wrapper around ANSI-aware visible length calculation."""
    return _visible_len(text)


def center_block(text: str, width: int | None = None) -> str:
    """Center a block of text using the terminal width (or provided width)."""
    trimmed = text.strip("\n")
    if not trimmed:
        return ""

    term_width = (
        width
        if width is not None
        else shutil.get_terminal_size((80, 20)).columns
    )
    lines = [line.rstrip() for line in trimmed.splitlines()]
    block_width = max(visible_length(line) for line in lines)
    padding = max((term_width - block_width) // 2, 0)
    centered = [" " * padding + line for line in lines]
    return "\n" + "\n".join(centered) + "\n"


def styled_divider(
    char: str = "─", length: int = 50, color: str = "green"
) -> str:
    """Create a colored divider line."""
    return color_text(char * length, color=color)


def styled_title(title: str, color: str = "green") -> str:
    """Create a simple colored title line."""
    return color_text(title, color=color)


def divider_line(length: int = 70, color: str = "green") -> str:
    """Helper to build a standardized divider line for logs."""
    return styled_divider(length=length, color=color)


def log_divider(
    logger: logging.Logger, length: int = 70, color: str = "green"
) -> None:
    """Render a divider via Rich (coordinates with live displays) and to log files."""
    # Console: Rich rule — goes through the singleton Console so it
    # will not corrupt an active Progress / Status bar.
    console = get_rich_console()
    console.rule(style=color)

    # File handlers: write a plain ASCII divider directly.
    plain_line = f"\n{'-' * length}\n"
    for handler in logger.handlers or logging.getLogger().handlers:
        if isinstance(handler, logging.FileHandler):
            try:
                stream = handler.stream
                if stream is None:
                    continue
                stream.write(plain_line)
                stream.flush()
            except Exception:
                pass


def add_padding_lines(lines: list[str], padding: int = 1) -> list[str]:
    """Insert blank lines between sections for readability."""
    pad = [""] * padding
    result: list[str] = []
    for i, line in enumerate(lines):
        result.append(line)
        if i != len(lines) - 1:
            result.extend(pad)
    return result


def styled_header(
    title: str, *, subtitle: str | None = None, width: int = 64
) -> str:
    """Create a boxed header for CLI commands."""
    visible_title = _visible_len(title)
    visible_sub = _visible_len(subtitle) if subtitle else 0
    inner_width = max(visible_title, visible_sub)

    # Box width accounts for borders + single-space padding on each side
    box_width = max(width, inner_width + 4)
    blank_space = " " * (box_width - 2)
    top = f"╔{'═' * (box_width - 2)}╗"
    mid = f"║ {title.center(box_width - 4)} ║"
    lines = [blank_space, top, mid]

    if subtitle:
        sub_line = f"║ {subtitle.center(box_width - 4)} ║"
        lines.append(sub_line)

    bottom = f"╚{'═' * (box_width - 2)}╝"
    lines.append(bottom)

    return "\n".join(color_text(line, color="green") for line in lines)


def bullet_line(
    label: str,
    value: str | None = None,
    *,
    color: str = "green",
    icon: str = "▸",
) -> str:
    """Format a colored bullet line with optional value."""
    label_part = f"{icon} {label}"
    if value is None:
        return color_text(label_part, color=color)
    return color_text(f"{label_part}: {value}", color=color)


def badge(text: str, *, color: str = "green") -> str:
    """Render a small badge-style label."""
    return color_text(f"[ {text} ]", color=color)


def success(message: str, *, icon: str = "✓") -> str:
    """Format a success message with green color and checkmark."""
    return color_text(f"{icon} {message}", color="green")


def warning(message: str, *, icon: str = "⚠") -> str:
    """Format a warning message with yellow color."""
    return color_text(f"{icon} {message}", color="yellow")


def error(message: str, *, icon: str = "✗") -> str:
    """Format an error message with red color."""
    return color_text(f"{icon} {message}", color="red")


def info_line(
    label: str, value: str | None = None, *, dim: bool = False
) -> str:
    """Format an info line with optional dim styling."""
    text = f"{label}: {value}" if value else label
    return color_text(text, color="dim" if dim else "cyan")


def format_path(path: str | Path, *, color: str = "green") -> str:
    """Format a path with color."""
    return color_text(str(path), color=color)


def format_number(num: int | float, *, color: str = "green") -> str:
    """Format a number with thousands separators and color."""
    if isinstance(num, float):
        formatted = f"{num:,.2f}"
    else:
        formatted = f"{num:,}"
    return color_text(formatted, color=color)


def format_size(size_bytes: int | float, *, color: str = "green") -> str:
    """Format byte size as human-readable string with color.

    Args:
        size_bytes: Size in bytes
        color: Color for the output

    Returns:
        Formatted size string (e.g., "1.5 MB")
    """
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            formatted = f"{size_bytes:.1f} {unit}"
            return color_text(formatted, color=color)
        size_bytes /= 1024
    formatted = f"{size_bytes:.1f} TB"
    return color_text(formatted, color=color)


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Get a logger instance.

    Args:
        name: Optional logger name for module-specific loggers.
              If None, returns the global application logger.

    Returns:
        Logger instance

    Usage:
        # Get global logger
        from sec_nlp.core.infra.logger import logger
        logger.info("Processing started")

        # Or use get_logger for module-specific loggers
        from sec_nlp.core.infra.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Processing started")
    """
    if name is None:
        return logger
    return logging.getLogger(name)
