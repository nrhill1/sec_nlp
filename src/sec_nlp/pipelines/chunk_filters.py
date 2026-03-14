# src/sec_nlp/pipelines/chunk_filters.py
"""Shared chunk filtering helpers for pipeline flows."""

from __future__ import annotations

from langchain_core.documents import Document

from sec_nlp.pipelines.runtime import get_accession_from_metadata

type AccessionCounts = dict[str, int]


def limit_docs_per_accession(
    docs: list[Document],
    max_chunks: int,
) -> tuple[list[Document], AccessionCounts, AccessionCounts]:
    """Limit documents per accession while preserving input order."""
    if max_chunks <= 0:
        return [], {}, {}

    kept_counts: AccessionCounts = {}
    skipped_counts: AccessionCounts = {}
    filtered: list[Document] = []

    for doc in docs:
        accession = get_accession_from_metadata(doc.metadata)
        kept = kept_counts.get(accession, 0)
        if kept >= max_chunks:
            skipped_counts[accession] = skipped_counts.get(accession, 0) + 1
            continue
        kept_counts[accession] = kept + 1
        filtered.append(doc)

    return filtered, kept_counts, skipped_counts
