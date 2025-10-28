import logging
from pathlib import Path
from typing import Literal

from _typeshed import Incomplete
from sec_nlp.core.config.settings import settings as settings

class ColoredFormatter(logging.Formatter):
    COLORS: Incomplete
    RESET: str
    def format(self, record: logging.LogRecord) -> str: ...

def setup_logging(level: str | int | None = None, format_type: Literal['simple', 'detailed', 'json'] | None = None, log_file: Path | str | None = None, enable_colors: bool = True) -> None: ...
def get_logger(name: str) -> logging.Logger: ...

class LogContext:
    logger: Incomplete
    level: Incomplete
    original_level: Incomplete
    def __init__(self, logger: logging.Logger | str, level: str | int) -> None: ...
    def __enter__(self) -> logging.Logger: ...
    def __exit__(self, *args: object) -> None: ...
