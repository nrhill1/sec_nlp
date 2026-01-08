# src/sec_nlp/pipelines/presets/analyze/utils.py
"""Shared helpers for analyze pipeline modules."""

from __future__ import annotations

import re

from sec_nlp.pipelines.types import MetadataMap


def resolve_symbol_for_output(
    fallback_symbol: str, *metas: MetadataMap | None
) -> str:
    """Pick the symbol to use for output routing, preferring metadata."""
    for meta in metas:
        if not meta:
            continue
        symbol = meta.get("symbol") or meta.get("ticker")
        if symbol:
            return str(symbol).strip().upper()

    return fallback_symbol.strip().upper()


DEFAULT_QUERY_STOPWORDS: set[str] = {
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

_QUERY_TERM_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def normalize_query_terms(
    query: str | None,
    *,
    min_len: int = 3,
    stopwords: set[str] | None = None,
) -> list[str]:
    """Extract normalized query terms for lexical overlap checks."""
    if not query:
        return []
    stop = stopwords or DEFAULT_QUERY_STOPWORDS
    terms: list[str] = []
    seen: set[str] = set()
    for raw in _QUERY_TERM_SPLIT_RE.split(query.lower()):
        term = raw.strip()
        if not term or len(term) < min_len or term in stop:
            continue
        if term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def query_term_overlap(
    query: str | None,
    content: str | None,
    *,
    min_len: int = 3,
    stopwords: set[str] | None = None,
) -> tuple[list[str], list[str], float]:
    """Return matched terms, missing terms, and overlap ratio."""
    terms = normalize_query_terms(query, min_len=min_len, stopwords=stopwords)
    if not terms or not content:
        return [], terms, 0.0
    haystack = content.lower()
    matched = [term for term in terms if term in haystack]
    missing = [term for term in terms if term not in haystack]
    ratio = len(matched) / len(terms) if terms else 0.0
    return matched, missing, ratio
