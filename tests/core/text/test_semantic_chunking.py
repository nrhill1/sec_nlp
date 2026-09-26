# tests/core/text/test_semantic_chunking.py
"""Tests for semantic chunk token-cap enforcement and config mapping."""

import pytest
from langchain_core.embeddings import Embeddings

import sec_nlp.core.text.semantic_chunking as semantic_chunking
from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.text.semantic_chunking import (
    SemanticChunker,
    SemanticChunkerConfig,
)
from sec_nlp.core.text.semantic_settings import SemanticChunkingSettings
from sec_nlp.types import JsonValue

type ChunkMetadata = dict[str, JsonValue]


class FakeEmbeddings(Embeddings):
    """Provide deterministic embeddings for semantic chunker tests."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one trivial vector per document."""
        return [[float(index + 1)] for index, _text in enumerate(texts)]

    def embed_query(self, text: str) -> list[float]:
        """Return a deterministic query vector."""
        return [float(len(text))]


class FakeExperimentalSemanticChunker:
    """Capture constructor kwargs and return deterministic semantic groups."""

    last_init_kwargs: dict[str, bool | int | float | str] = {}

    def __init__(
        self,
        _embedder: Embeddings,
        *,
        breakpoint_threshold_type: str | None = None,
        breakpoint_threshold_amount: float | None = None,
        buffer_size: int | None = None,
        number_of_chunks: int | None = None,
        sentence_split_regex: str | None = None,
        min_chunk_size: int | None = None,
        add_start_index: bool | None = None,
    ) -> None:
        """Store constructor kwargs for later assertions."""
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
        """Split each text into two broad semantic groups."""
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
            midpoint = max(1, len(parts) // 2)
            left = ". ".join(parts[:midpoint]).strip() + "."
            right = ". ".join(parts[midpoint:]).strip() + "."
            docs.append(Document(page_content=left, metadata=metadata))
            if len(parts) > 1:
                docs.append(Document(page_content=right, metadata=metadata))
        return docs


@pytest.fixture
def patched_semantic_chunker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the experimental chunker import to use the local fake."""
    monkeypatch.setattr(
        semantic_chunking,
        "_load_experimental_chunker",
        lambda: FakeExperimentalSemanticChunker,
    )


def test_settings_map_max_chunk_tokens_into_runtime_config() -> None:
    """Map shared settings token caps into the runtime chunker config."""
    settings = SemanticChunkingSettings(
        max_chunk_tokens=192,
        min_chunk_sentences=2,
        max_chunk_sentences=12,
    )

    config = SemanticChunkerConfig.from_settings(settings)

    assert config.max_chunk_tokens == 192
    assert config.min_chunk_sentences == 2
    assert config.max_chunk_sentences == 12


def test_constructor_passes_supported_kwargs(
    patched_semantic_chunker: None,
) -> None:
    """Forward supported LangChain constructor kwargs unchanged."""
    _ = patched_semantic_chunker
    config = SemanticChunkerConfig(
        breakpoint_threshold_type="gradient",
        breakpoint_threshold_amount=4.5,
        window_size=3,
        number_of_chunks=8,
        sentence_split_regex=r"(?<=[.?!])\s+",
        min_chunk_size=96,
        add_start_index=True,
        max_chunk_tokens=144,
    )

    chunker = SemanticChunker(embedder=FakeEmbeddings(), config=config)

    assert chunker.config.max_chunk_tokens == 144
    assert (
        FakeExperimentalSemanticChunker.last_init_kwargs[
            "breakpoint_threshold_type"
        ]
        == "gradient"
    )
    assert FakeExperimentalSemanticChunker.last_init_kwargs[
        "breakpoint_threshold_amount"
    ] == pytest.approx(4.5)
    assert FakeExperimentalSemanticChunker.last_init_kwargs["buffer_size"] == 3
    assert (
        FakeExperimentalSemanticChunker.last_init_kwargs["number_of_chunks"]
        == 8
    )
    assert (
        FakeExperimentalSemanticChunker.last_init_kwargs["sentence_split_regex"]
        == r"(?<=[.?!])\s+"
    )
    assert (
        FakeExperimentalSemanticChunker.last_init_kwargs["min_chunk_size"] == 96
    )
    assert (
        FakeExperimentalSemanticChunker.last_init_kwargs["add_start_index"]
        is True
    )


def test_semantic_chunker_splits_groups_that_exceed_token_cap(
    patched_semantic_chunker: None,
) -> None:
    """Split large semantic groups further when the token cap is exceeded."""
    _ = patched_semantic_chunker
    chunker = SemanticChunker(
        embedder=FakeEmbeddings(),
        config=SemanticChunkerConfig(
            min_chunk_sentences=1,
            max_chunk_sentences=10,
            max_chunk_tokens=4,
        ),
    )

    chunks = chunker.split_documents(
        [
            Document(
                page_content=(
                    "Alpha beta gamma. Delta epsilon zeta. "
                    "Eta theta iota. Kappa lambda mu."
                ),
                metadata={"source": "fcx.html"},
            )
        ]
    )

    assert len(chunks) == 4
    assert [chunk.page_content for chunk in chunks] == [
        "Alpha beta gamma.",
        "Delta epsilon zeta.",
        "Eta theta iota.",
        "Kappa lambda mu.",
    ]
    assert all(chunk.metadata.get("token_count") == 4 for chunk in chunks)
    assert all(chunk.metadata.get("source") == "fcx.html" for chunk in chunks)
