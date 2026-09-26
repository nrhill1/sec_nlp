# src/sec_nlp/core/news/normalization.py
"""Normalize article identities and publication dates across news consumers.

Dates are parsed before comparisons. URL identities drop tracking fields, and
headline title identities are qualified by UTC publication date so recurring
releases do not disappear. Undated articles use only their source URL identity.
"""

import logging
import re
import unicodedata
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import HttpUrl, ValidationError

logger = logging.getLogger(__name__)
_TRACKING_KEYS = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "ref_src",
        "igshid",
    }
)


def parse_timestamp(value: str | None) -> datetime | None:
    """Normalize ISO or RFC 2822 dates, treating timezone-free dates as UTC."""
    if value is None or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        logger.debug(
            "News timestamp is not ISO formatted; trying RFC 2822",
            exc_info=True,
        )
        try:
            parsed = parsedate_to_datetime(value.strip())
        except (ValueError, TypeError, OverflowError):
            logger.debug(
                "Keeping headline with an unknown publication date",
                exc_info=True,
            )
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    try:
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        logger.debug(
            "Keeping headline with an invalid timezone date", exc_info=True
        )
        return None


def safe_url(value: str) -> HttpUrl | None:
    """Validate an HTTP article URL and remove fragment and tracking fields."""
    try:
        validated = HttpUrl(value.strip())
        if validated.username is not None or validated.password is not None:
            return None
        parsed = urlsplit(str(validated))
        query = urlencode(
            sorted(
                (name, content)
                for name, content in parse_qsl(
                    parsed.query, keep_blank_values=True
                )
                if not name.casefold().startswith("utm_")
                and name.casefold() not in _TRACKING_KEYS
            )
        )
        return HttpUrl(
            urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))
        )
    except (ValidationError, ValueError):
        logger.debug(
            "Ignoring headline with an invalid article URL", exc_info=True
        )
        return None


def url_key(value: HttpUrl) -> str:
    """Return an article identity that ignores transport scheme and trailing slash."""
    parsed = urlsplit(str(safe_url(str(value)) or value))
    return urlunsplit(
        (
            "",
            parsed.netloc.casefold(),
            parsed.path.rstrip("/"),
            parsed.query,
            "",
        )
    )


def title_key(value: str) -> str:
    """Normalize headline case, punctuation, Unicode presentation, and spacing."""
    return " ".join(
        re.findall(r"\w+", unicodedata.normalize("NFKC", value).casefold())
    )


def dated_title_key(title: str, published_at: datetime | None) -> str | None:
    """Return a title identity only when its source publication date is known.

    Args:
        title: Article headline to normalize.
        published_at: Parsed, timezone-aware source publication timestamp.

    Returns:
        UTC date and normalized title, or no title identity for an undated item.
    """
    normalized = title_key(title)
    if published_at is None or not normalized:
        return None
    return f"{published_at.astimezone(UTC).date().isoformat()}:{normalized}"
