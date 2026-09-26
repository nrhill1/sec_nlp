# tests/pipelines/presets/test_analyze_chunking.py
"""Tests for section-aware chunking in the analyze pipeline."""

import pytest
from langchain_core.embeddings import Embeddings

import sec_nlp.core.text.semantic_chunking as semantic_chunking
from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.text.filters import create_exhibit_filter
from sec_nlp.core.text.section_extractor import SectionExtractor
from sec_nlp.core.text.semantic_chunking import (
    SemanticChunker,
    SemanticChunkerConfig,
)
from sec_nlp.types import JsonValue

type ChunkMetadata = dict[str, JsonValue]


class FakeEmbeddings(Embeddings):
    """Minimal embeddings implementation for semantic chunker tests."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return deterministic vectors with one dimension per text."""
        return [[float(len(texts))] for _text in texts]

    def embed_query(self, text: str) -> list[float]:
        """Return deterministic query vector."""
        return [float(len(text))]


class FakeExperimentalSemanticChunker:
    """Test double for LangChain experimental SemanticChunker."""

    last_init_kwargs: dict[str, bool | int | float | str] = {}

    def __init__(
        self,
        _embedder,
        *,
        breakpoint_threshold_type: str | None = None,
        breakpoint_threshold_amount: float | None = None,
        buffer_size: int | None = None,
        number_of_chunks: int | None = None,
        sentence_split_regex: str | None = None,
        min_chunk_size: int | None = None,
        add_start_index: bool | None = None,
    ) -> None:
        """Capture initialization kwargs for assertions."""
        kwargs: dict[str, bool | int | float | str] = {}
        if breakpoint_threshold_type is not None:
            kwargs["breakpoint_threshold_type"] = breakpoint_threshold_type
        if breakpoint_threshold_amount is not None:
            kwargs["breakpoint_threshold_amount"] = breakpoint_threshold_amount
        if buffer_size is not None:
            kwargs["buffer_size"] = buffer_size
        if number_of_chunks is not None:
            kwargs["number_of_chunks"] = number_of_chunks
        if sentence_split_regex is not None:
            kwargs["sentence_split_regex"] = sentence_split_regex
        if min_chunk_size is not None:
            kwargs["min_chunk_size"] = min_chunk_size
        if add_start_index is not None:
            kwargs["add_start_index"] = add_start_index
        self.__class__.last_init_kwargs = kwargs

    def create_documents(
        self,
        texts: list[str],
        metadatas: list[ChunkMetadata] | None = None,
    ) -> list[Document]:
        """Return deterministic two-part chunks for each input text."""
        docs: list[Document] = []
        for index, text in enumerate(texts):
            metadata = (
                dict(metadatas[index])
                if metadatas is not None and index < len(metadatas)
                else {}
            )
            parts = [part.strip() for part in text.split(".") if part.strip()]
            if not parts:
                continue
            if len(parts) == 1:
                docs.append(
                    Document(page_content=f"{parts[0]}.", metadata=metadata)
                )
                continue
            midpoint = max(1, len(parts) // 2)
            left = ". ".join(parts[:midpoint]).strip() + "."
            right = ". ".join(parts[midpoint:]).strip() + "."
            docs.append(Document(page_content=left, metadata=metadata))
            docs.append(Document(page_content=right, metadata=metadata))
        return docs


@pytest.fixture
def patched_semantic_chunker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch semantic chunker loader to avoid external dependency in tests."""
    monkeypatch.setattr(
        semantic_chunking,
        "_load_experimental_chunker",
        lambda: FakeExperimentalSemanticChunker,
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
        assert config.breakpoint_threshold_type == "percentile"
        assert config.breakpoint_threshold_amount is None
        assert config.number_of_chunks is None
        assert config.sentence_split_regex == r"(?<=[.?!])\s+"
        assert config.min_chunk_size is None
        assert config.add_start_index is False

    def test_custom_values(self) -> None:
        """Custom config values are respected."""
        config = SemanticChunkerConfig(
            min_chunk_sentences=5,
            max_chunk_sentences=100,
            similarity_threshold=0.7,
            window_size=3,
            embedding_batch_size=16,
            breakpoint_threshold_type="gradient",
            breakpoint_threshold_amount=5.5,
            number_of_chunks=20,
            sentence_split_regex=r"(?<=[.!?])\s+",
            min_chunk_size=120,
            add_start_index=True,
        )
        assert config.min_chunk_sentences == 5
        assert config.max_chunk_sentences == 100
        assert config.similarity_threshold == 0.7
        assert config.window_size == 3
        assert config.embedding_batch_size == 16
        assert config.breakpoint_threshold_type == "gradient"
        assert config.breakpoint_threshold_amount == 5.5
        assert config.number_of_chunks == 20
        assert config.sentence_split_regex == r"(?<=[.!?])\s+"
        assert config.min_chunk_size == 120
        assert config.add_start_index is True


class TestSemanticChunkerMapping:
    """Tests for semantic chunker wrapper configuration mapping."""

    def test_constructor_maps_threshold_settings(
        self, patched_semantic_chunker: None
    ) -> None:
        """Map local config values to experimental chunker constructor kwargs."""
        _ = patched_semantic_chunker
        config = SemanticChunkerConfig(
            similarity_threshold=0.6,
            window_size=4,
            breakpoint_threshold_type="gradient",
            breakpoint_threshold_amount=4.2,
            number_of_chunks=6,
            sentence_split_regex=r"(?<=[.?!])\s+",
            min_chunk_size=90,
            add_start_index=True,
        )
        _ = SemanticChunker(embedder=FakeEmbeddings(), config=config)
        assert (
            FakeExperimentalSemanticChunker.last_init_kwargs.get(
                "breakpoint_threshold_type"
            )
            == "gradient"
        )
        assert FakeExperimentalSemanticChunker.last_init_kwargs.get(
            "breakpoint_threshold_amount"
        ) == pytest.approx(4.2)
        assert (
            FakeExperimentalSemanticChunker.last_init_kwargs.get("buffer_size")
            == 4
        )
        assert (
            FakeExperimentalSemanticChunker.last_init_kwargs.get(
                "number_of_chunks"
            )
            == 6
        )
        assert (
            FakeExperimentalSemanticChunker.last_init_kwargs.get(
                "sentence_split_regex"
            )
            == r"(?<=[.?!])\s+"
        )
        assert (
            FakeExperimentalSemanticChunker.last_init_kwargs.get(
                "min_chunk_size"
            )
            == 90
        )
        assert (
            FakeExperimentalSemanticChunker.last_init_kwargs.get(
                "add_start_index"
            )
            is True
        )


class TestSemanticChunker:
    """Tests for SemanticChunker."""

    def test_small_text_single_chunk(
        self, patched_semantic_chunker: None
    ) -> None:
        """Text smaller than min_chunk_sentences returns single chunk."""
        _ = patched_semantic_chunker
        config = SemanticChunkerConfig(min_chunk_sentences=5)
        chunker = SemanticChunker(embedder=FakeEmbeddings(), config=config)

        text = "First sentence. Second sentence."
        chunks = chunker.split_text(text)

        assert len(chunks) == 1
        assert "First sentence" in chunks[0]

    def test_empty_text_returns_empty(
        self, patched_semantic_chunker: None
    ) -> None:
        """Empty text returns empty list."""
        _ = patched_semantic_chunker
        chunker = SemanticChunker(embedder=FakeEmbeddings())
        assert chunker.split_text("") == []
        assert chunker.split_text("   ") == []

    def test_split_documents_preserves_metadata(
        self, patched_semantic_chunker: None
    ) -> None:
        """split_documents preserves original metadata and adds chunk metadata."""
        _ = patched_semantic_chunker
        config = SemanticChunkerConfig(
            min_chunk_sentences=1, max_chunk_sentences=2
        )
        chunker = SemanticChunker(embedder=FakeEmbeddings(), config=config)

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

    def test_repr(self, patched_semantic_chunker: None) -> None:
        """SemanticChunker has informative repr."""
        _ = patched_semantic_chunker
        config = SemanticChunkerConfig(
            similarity_threshold=0.6,
            min_chunk_sentences=4,
            max_chunk_sentences=40,
        )
        chunker = SemanticChunker(embedder=FakeEmbeddings(), config=config)
        repr_str = repr(chunker)

        assert "SemanticChunker" in repr_str
        assert "0.6" in repr_str
        assert "4" in repr_str
        assert "40" in repr_str
