# src/sec_nlp/pipelines/utils.py
"""Utility functions shared across pipeline implementations."""

import re

_EMAIL_PATTERN: re.Pattern[str] = re.compile(
    r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
)


def is_valid_email(email: str) -> bool:
    """Check if the provided string is a valid email address."""
    return bool(_EMAIL_PATTERN.match(email))


def safe_filename(s: str, allow: str = r"a-zA-Z0-9._-") -> str:
    """Sanitize string for use in filenames."""
    return re.sub(rf"[^{allow}]+", "_", s)[:120]


def slugify(s: str) -> str:
    """Convert string to URL-safe slug."""
    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")
