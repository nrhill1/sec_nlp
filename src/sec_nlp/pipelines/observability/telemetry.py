"""Shared telemetry helpers for pipelines (chunk stats, document metadata).

Chunk stats now report both character length and sentence count metrics,
reflecting the switch to sentence-based chunking.
"""

from __future__ import annotations

import statistics

from langchain_core.documents import Document

from sec_nlp.core.infra.logger import color_text, logger
from sec_nlp.core.text.keyword import FilterStats


def log_chunk_length_stats(
    *,
    label: str | None,
    symbol: str | None,
    accession: str | None,
    docs: list[Document],
    keyword_field: str | None = None,
    prefix_color: str | None = None,
) -> None:
    """Log chunk statistics for a group of documents.

    Reports:
    - Character length stats (chars): total characters per chunk
    - Sentence count stats (sents): sentences per chunk (from metadata)
    - Keyword scores (optional): if keyword_field is provided
    """
    # Character lengths
    char_lengths = [len(d.page_content or "") for d in docs]

    # Sentence counts from metadata (added by SentenceSplitter)
    sentence_counts: list[int] = []
    for d in docs:
        meta = d.metadata or {}
        sent_count = meta.get("sentence_count")
        if sent_count is not None:
            try:
                sentence_counts.append(int(sent_count))
            except (TypeError, ValueError):
                pass

    # Keyword scores
    keyword_scores: list[float] = []
    if keyword_field:
        for d in docs:
            meta = d.metadata or {}
            try:
                keyword_scores.append(float(meta.get(keyword_field, 0.0)))
            except Exception:
                continue

    # Build prefix for log messages
    prefix_parts = []
    if label:
        prefix_parts.append(label.capitalize())
    if symbol:
        prefix_parts.append(str(symbol))
    if accession:
        prefix_parts.append(str(accession))
    prefix = "/".join(prefix_parts) if prefix_parts else "chunks"
    if prefix_color:
        prefix = color_text(prefix, color=prefix_color)

    if not char_lengths:
        logger.info("%s chunk stats: none", prefix)
        return

    # Log character length stats
    logger.info(
        "%s chunk stats (chars): n=%d min=%d max=%d mean=%.0f median=%.0f total=%.1fK",
        prefix,
        len(char_lengths),
        min(char_lengths),
        max(char_lengths),
        statistics.mean(char_lengths),
        statistics.median(char_lengths),
        sum(char_lengths) / 1000,
    )

    # Log sentence count stats if available
    if sentence_counts:
        logger.info(
            "%s chunk stats (sents): n=%d min=%d max=%d mean=%.1f median=%.1f total=%d",
            prefix,
            len(sentence_counts),
            min(sentence_counts),
            max(sentence_counts),
            statistics.mean(sentence_counts),
            statistics.median(sentence_counts),
            sum(sentence_counts),
        )

    # Log keyword scores if provided
    if keyword_scores:
        logger.info(
            "%s chunk keyword stats (%s): n=%d min=%.2f max=%.2f mean=%.2f median=%.2f",
            prefix,
            keyword_field,
            len(keyword_scores),
            min(keyword_scores),
            max(keyword_scores),
            statistics.mean(keyword_scores),
            statistics.median(keyword_scores),
        )


def log_llm_inputs(batch: list[Document], docs: list[Document]) -> None:
    """Emit DEBUG traces for LLM inputs and chunk previews."""
    import hashlib

    for idx, (item, _doc) in enumerate(zip(batch, docs, strict=True)):
        text = getattr(item, "chunk", "") or ""
        symbol = getattr(item, "symbol", "unknown")
        chunk_hash = hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[
            :8
        ]
        preview = text[:400].replace("\n", " ")
        logger.debug(
            "LLM input [symbol=%s idx=%d hash=%s len=%d]: %s",
            symbol,
            idx,
            chunk_hash,
            len(text),
            preview,
        )


def log_exhibit_stats(
    *,
    symbol: str,
    chunk_count: int,
    sections_found: int,
    exhibit_docs: int,
    html_files: int,
    accession_count: int | None = None,
    filtered_chunk_count: int | None = None,
    prefilter_skips: dict[str, int] | None = None,
) -> None:
    """Log a concise summary of extracted Exhibit 10 content."""
    parts = [
        f"chunks={chunk_count}",
        f"sections={sections_found}",
        f"exhibit_docs={exhibit_docs}",
        f"html_files={html_files}",
    ]
    if accession_count is not None:
        parts.append(f"accessions={accession_count}")
    if filtered_chunk_count is not None:
        parts.append(f"filtered_chunks={filtered_chunk_count}")
    if prefilter_skips:
        skip_text = ", ".join(
            f"{reason}:{count}"
            for reason, count in sorted(prefilter_skips.items())
        )
        parts.append(f"prefilter_skips={skip_text}")

    logger.info("Exhibit 10 stats for %s: %s", symbol, " ".join(parts))


def log_document_metadata(
    *,
    symbol: str,
    accession_number: str | None,
    filename: str,
    filing_date: str | None,
    source: str,
    exhibit_number: str | None = None,
) -> None:
    """Log per-document metadata as it enters processing."""
    formatted_date = filing_date
    logger.debug(
        "Doc for %s: accession=%s file=%s source=%s exhibit=%s filing_date=%s",
        symbol,
        accession_number or "unknown",
        filename,
        source,
        exhibit_number or "n/a",
        formatted_date,
    )


def log_filter_stats(
    *,
    symbol: str | None,
    stats: FilterStats,
) -> None:
    """Log concise keyword filter results for a batch of chunks."""
    prefix = f"{symbol}" if symbol else "chunks"
    logger.info(
        (
            "Chunk filter for %s: kept=%d/%d keyword=%d fallback=%d "
            "skipped_short=%d skipped_dupe=%d capped=%d"
        ),
        prefix,
        stats.kept,
        stats.total,
        stats.keyword_hits,
        stats.fallback_kept,
        stats.skipped_short,
        stats.skipped_dupe,
        stats.capped,
    )
