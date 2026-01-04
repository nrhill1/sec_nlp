# tests/pipelines/presets/test_analyze_chunking.py
"""Tests for section-aware chunking in the analyze pipeline."""

from sec_nlp.core.text.filters import create_exhibit_filter
from sec_nlp.core.text.section_extractor import SectionExtractor


def test_section_extractor_chunks_preserve_section_metadata() -> None:
    """Ensure sections are chunked separately with section metadata preserved."""
    # Two exhibits with a couple of sentences each
    content = (
        "EXHIBIT 10\nFirst sentence. Second sentence.\n"
        "EXHIBIT 21\nThird sentence. Fourth sentence."
    )
    extractor = SectionExtractor(
        section_filter=create_exhibit_filter(["10", "21"]),
        max_section_length=10_000,
        detect_boundaries=True,
    )

    chunks = extractor.extract_and_chunk(
        content,
        metadata={"accession_number": "0000000000-00-000000"},
        chunk_size=1,  # one sentence per chunk to preserve meaning
        chunk_overlap=0,
    )

    # We expect four sentence-level chunks across two sections
    assert len(chunks) == 4

    section_numbers = {chunk.metadata.get("section_number") for chunk in chunks}
    assert section_numbers == {"10", "21"}

    # Each chunk should carry sentence_count and chunk_index metadata
    for chunk in chunks:
        assert chunk.metadata.get("sentence_count") == 1
        assert (
            "chunk_index" in chunk.metadata
            or chunk.metadata.get("chunk_index") == 0
        )
