"""Shared lexical tokenization helpers for retrieve pipeline."""

from __future__ import annotations

import re
from collections.abc import Collection

_WORD_RE = re.compile(r"[a-z0-9]+")

DEFAULT_QUERY_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "was",
        "were",
        "with",
    }
)


def extract_query_terms(
    text: str,
    *,
    min_len: int = 3,
    stopwords: Collection[str] | None = None,
) -> set[str]:
    """Extract normalized lexical terms from text."""
    terms: set[str] = set()
    for token in _WORD_RE.findall(text.casefold()):
        if len(token) < min_len:
            continue
        if stopwords is not None and token in stopwords:
            continue
        terms.add(token)
    return terms
