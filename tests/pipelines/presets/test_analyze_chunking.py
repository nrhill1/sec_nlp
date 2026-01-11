# tests/pipelines/presets/test_analyze_chunking.py
"""Tests for section-aware chunking in the analyze pipeline."""

from unittest.mock import MagicMock

import numpy as np
import pytest
from langchain_core.documents import Document

from sec_nlp.core.text.filters import create_exhibit_filter
from sec_nlp.core.text.section_extractor import SectionExtractor
from sec_nlp.core.text.semantic_chunking import (
    SemanticChunker,
    SemanticChunkerConfig,
    _cosine_similarity,
)


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


class TestSemanticChunkerConfig:
    """Tests for SemanticChunkerConfig defaults and validation."""

    def test_default_values(self) -> None:
        """Default config values are sensible."""
        config = SemanticChunkerConfig()
        assert config.min_chunk_sentences == 3
        assert config.max_chunk_sentences == 50
        assert config.similarity_threshold == 0.5
        assert config.window_size == 2
        assert config.embedding_batch_size == 32

    def test_custom_values(self) -> None:
        """Custom config values are respected."""
        config = SemanticChunkerConfig(
            min_chunk_sentences=5,
            max_chunk_sentences=100,
            similarity_threshold=0.7,
            window_size=3,
            embedding_batch_size=16,
        )
        assert config.min_chunk_sentences == 5
        assert config.max_chunk_sentences == 100
        assert config.similarity_threshold == 0.7
        assert config.window_size == 3
        assert config.embedding_batch_size == 16


class TestCosimeSimilarity:
    """Tests for cosine similarity helper."""

    def test_identical_vectors(self) -> None:
        """Identical vectors have similarity 1.0."""
        vec = np.array([1.0, 2.0, 3.0])
        assert _cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        """Orthogonal vectors have similarity 0.0."""
        vec_a = np.array([1.0, 0.0])
        vec_b = np.array([0.0, 1.0])
        assert _cosine_similarity(vec_a, vec_b) == pytest.approx(0.0)

    def test_opposite_vectors(self) -> None:
        """Opposite vectors have similarity -1.0."""
        vec_a = np.array([1.0, 0.0])
        vec_b = np.array([-1.0, 0.0])
        assert _cosine_similarity(vec_a, vec_b) == pytest.approx(-1.0)

    def test_zero_vector(self) -> None:
        """Zero vector returns 0.0 similarity."""
        vec_a = np.array([1.0, 2.0])
        vec_b = np.array([0.0, 0.0])
        assert _cosine_similarity(vec_a, vec_b) == 0.0


class TestSemanticChunker:
    """Tests for SemanticChunker."""

    @pytest.fixture
    def mock_embedder(self) -> MagicMock:
        """Create a mock embedder that returns predictable embeddings."""
        embedder = MagicMock()
        # Return different embeddings for different texts to simulate topic shifts
        call_count = 0

        def embed_documents(texts: list[str]) -> list[list[float]]:
            nonlocal call_count
            results: list[list[float]] = []
            for _ in texts:
                # Alternate between two distinct embedding clusters
                if call_count % 4 < 2:
                    results.append([1.0, 0.0, 0.0])
                else:
                    results.append([0.0, 1.0, 0.0])
                call_count += 1
            return results

        embedder.embed_documents = embed_documents
        return embedder

    def test_small_text_single_chunk(self, mock_embedder: MagicMock) -> None:
        """Text smaller than min_chunk_sentences returns single chunk."""
        config = SemanticChunkerConfig(min_chunk_sentences=5)
        chunker = SemanticChunker(embedder=mock_embedder, config=config)

        text = "First sentence. Second sentence."
        chunks = chunker.split_text(text)

        assert len(chunks) == 1
        assert "First sentence" in chunks[0]

    def test_empty_text_returns_empty(self, mock_embedder: MagicMock) -> None:
        """Empty text returns empty list."""
        chunker = SemanticChunker(embedder=mock_embedder)
        assert chunker.split_text("") == []
        assert chunker.split_text("   ") == []

    def test_split_documents_preserves_metadata(
        self, mock_embedder: MagicMock
    ) -> None:
        """split_documents preserves original metadata and adds chunk metadata."""
        config = SemanticChunkerConfig(
            min_chunk_sentences=1, max_chunk_sentences=2
        )
        chunker = SemanticChunker(embedder=mock_embedder, config=config)

        doc = Document(
            page_content="First sentence. Second sentence. Third sentence. Fourth sentence.",
            metadata={"source": "test.txt", "accession": "12345"},
        )
        chunks = chunker.split_documents([doc])

        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.metadata.get("source") == "test.txt"
            assert chunk.metadata.get("accession") == "12345"
            assert "chunk_index" in chunk.metadata
            assert "sentence_count" in chunk.metadata
            assert chunk.metadata.get("chunking_mode") == "semantic"

    def test_repr(self, mock_embedder: MagicMock) -> None:
        """SemanticChunker has informative repr."""
        config = SemanticChunkerConfig(
            similarity_threshold=0.6,
            min_chunk_sentences=4,
            max_chunk_sentences=40,
        )
        chunker = SemanticChunker(embedder=mock_embedder, config=config)
        repr_str = repr(chunker)

        assert "SemanticChunker" in repr_str
        assert "0.6" in repr_str
        assert "4" in repr_str
        assert "40" in repr_str
