# src/sec_nlp/pipelines/presets/analyze/steps/preprocess/topic_scoring.py
"""Topic scoring utilities for analyze chunks.

This module provides utilities for scoring documents based on topic/keyword
matching. It uses the Rust-based ranking module when available for better
performance, with fallback to Python implementations.
"""

from __future__ import annotations

from collections.abc import Iterable

from langchain_core.documents import Document

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.text.keyword import KeywordMatcher
from sec_nlp.core.text.ranking import (
    EFTS_AVAILABLE,
    rank_documents as rust_rank_documents,
    score_document as rust_score_document,
)


def normalize_topics(topics: Iterable[str] | None) -> list[str]:
    """Normalize topic inputs by filtering empty/non-string values."""
    cleaned: list[str] = []
    for topic in topics or []:
        if not isinstance(topic, str):
            continue
        stripped = topic.strip()
        if stripped:
            cleaned.append(stripped)
    return cleaned


def build_topic_matcher(
    topics: Iterable[str] | None,
) -> KeywordMatcher | None:
    """Create a reusable keyword matcher for topic scoring.

    Note: When the Rust EFTS extension is available, this matcher is only
    used as a fallback. The Rust-based scoring functions are preferred.
    """
    cleaned = normalize_topics(topics)
    if not cleaned:
        return None
    return KeywordMatcher(cleaned, case_insensitive=True)


def count_topics(
    content: str | None,
    *,
    topics: list[str],
    matcher: KeywordMatcher | None,
) -> tuple[dict[str, int], int]:
    """Count topic occurrences in content.

    Uses Rust backend when available for better performance.

    Args:
        content: Text content to search.
        topics: List of topic keywords.
        matcher: Optional KeywordMatcher (fallback if Rust unavailable).

    Returns:
        Tuple of (keyword_counts, total_hits).
    """
    if not content:
        return {}, 0

    # Use Rust backend when available
    if EFTS_AVAILABLE and topics:
        result = rust_score_document(content, topics)
        return result.keyword_counts, result.total_hits

    # Fallback to Python KeywordMatcher
    if matcher:
        return matcher.count(content)

    if not topics:
        return {}, 0

    counts: dict[str, int] = {}
    lower_content = content.lower()
    for topic in topics:
        if not isinstance(topic, str):
            continue
        t = topic.lower().strip()
        if not t:
            continue
        counts[t] = lower_content.count(t)

    total_hits = sum(counts.values())
    return counts, total_hits


def score_documents(
    docs: list[Document],
    *,
    topics: Iterable[str] | None,
    matcher: KeywordMatcher | None = None,
    min_hits: int = 0,
    prioritize: bool = True,
) -> list[Document]:
    """Attach topic hit metadata and filter docs by hit count.

    Uses Rust-based ranking when available for better performance on large
    document sets.

    Args:
        docs: List of documents to score.
        topics: Topic keywords to search for.
        matcher: Optional KeywordMatcher (fallback if Rust unavailable).
        min_hits: Minimum hits required to include a document.
        prioritize: Whether to sort by score (descending).

    Returns:
        Filtered and optionally sorted list of documents with metadata.
    """
    cleaned = normalize_topics(topics)
    if not docs or not cleaned:
        return docs if docs else []

    # Use Rust-based ranking for better performance
    if EFTS_AVAILABLE:
        result = rust_rank_documents(
            docs,
            cleaned,
            min_hits=min_hits,
            top_n=None,  # Return all matching docs
            prioritize=prioritize,
        )
        logger.info(
            "Topic scoring (Rust): kept %d/%d chunks (min_hits=%d)",
            len(result),
            len(docs),
            min_hits,
        )
        return result

    # Fallback to Python implementation
    if matcher is None:
        matcher = build_topic_matcher(cleaned)

    scored_docs: list[tuple[Document, int]] = []
    for doc in docs:
        counts, total_hits = count_topics(
            doc.page_content,
            topics=cleaned,
            matcher=matcher,
        )
        doc.metadata = {
            **(doc.metadata or {}),
            "topic_hits": [k for k, v in counts.items() if v > 0],
            "topic_hits_detail": counts,
            "topic_score": total_hits,
        }
        if total_hits < min_hits:
            continue
        scored_docs.append((doc, total_hits))

    if scored_docs:
        if prioritize:
            scored_docs.sort(key=lambda t: t[1], reverse=True)
        filtered = [doc for doc, _ in scored_docs]
        logger.info(
            "Topic scoring (Python): kept %d/%d chunks (min_hits=%d)",
            len(filtered),
            len(docs),
            min_hits,
        )
        return filtered

    return []
