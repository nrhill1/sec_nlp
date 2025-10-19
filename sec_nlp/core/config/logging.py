# sec_nlp/config/logging.py
"""Centralized logging configuration."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Literal

from sec_nlp.core.config.settings import settings


class ColoredFormatter(logging.Formatter):
    """Colored formatter for console output."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Add color to log level."""
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}"
        return super().format(record)


def setup_logging(
    level: str | int | None = None,
    format_type: Literal["simple", "detailed", "json"] | None = None,
    log_file: Path | str | None = None,
    enable_colors: bool = True,
) -> None:
    """
    Configure application-wide logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) or int
        format_type: Log format style
        log_file: Optional file path to write logs to
        enable_colors: Enable colored output for console (ignored if log_file)

    Usage:
        # Simple setup using defaults from settings
        setup_logging()

        # Custom setup
        setup_logging(level="DEBUG", format_type="detailed")

        # With file output
        setup_logging(log_file="logs/app.log")
    """

    # Determine log level
    if level is None:
        level = settings.log_level
    if isinstance(level, str):
        level = getattr(logging, level.upper())

    # Determine format
    if format_type is None:
        format_type = settings.log_format

    # Format strings
    formats = {
        "simple": "%(levelname)s - %(message)s",
        "detailed": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "json": '{"time":"%(asctime)s","name":"%(name)s","level":"%(levelname)s","message":"%(message)s"}',
    }

    log_format = formats.get(format_type, formats["simple"])
    date_format = "%Y-%m-%d %H:%M:%S"

    # Create formatter
    if enable_colors and log_file is None and format_type != "json":
        formatter = ColoredFormatter(log_format, datefmt=date_format)
    else:
        formatter = logging.Formatter(log_format, datefmt=date_format)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(level)
        # File logs always use plain formatter (no colors)
        file_formatter = logging.Formatter(log_format, datefmt=date_format)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("torch").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    root_logger.info(
        "Logging configured: level=%s, format=%s, file=%s",
        logging.getLevelName(level),
        format_type,
        log_file or "console only",
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance

    Usage:
        from sec_nlp.pipelines.utils.logging import get_logger

        logger = get_logger(__name__)
        logger.info("Processing started")
    """
    return logging.getLogger(name)


class LogContext:
    """Context manager for temporary log level changes."""

    def __init__(self, logger: logging.Logger | str, level: str | int):
        """
        Args:
            logger: Logger instance or name
            level: Temporary log level
        """
        if isinstance(logger, str):
            logger = logging.getLogger(logger)
        self.logger = logger
        self.level = level if isinstance(level, int) else getattr(logging, level.upper())
        self.original_level = logger.level

    def __enter__(self) -> logging.Logger:
        """Set temporary log level."""
        self.logger.setLevel(self.level)
        return self.logger

    def __exit__(self, *args) -> None:
        """Restore original log level."""
        self.logger.setLevel(self.original_level)
