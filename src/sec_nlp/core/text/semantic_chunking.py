# src/sec_nlp/core/text/semantic_chunking.py
"""Semantic chunking using embeddings to find natural topic boundaries.

Chunks text by detecting semantic shifts using embedding similarity,
preserving topical coherence within chunks.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from langchain_core.documents import Document
from langchain_ollama.embeddings import OllamaEmbeddings

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.text.chunking import _NLTK_AVAILABLE, _fallback_sent_tokenize

if _NLTK_AVAILABLE:
    from nltk.tokenize import sent_tokenize


@dataclass(frozen=True)
class SemanticChunkerConfig:
    """Configuration for semantic chunking."""

    min_chunk_sentences: int = 3
    """Minimum sentences per chunk to avoid overly fragmented output."""

    max_chunk_sentences: int = 50
    """Maximum sentences per chunk to prevent overly large chunks."""

    similarity_threshold: float = 0.5
    """Similarity below this triggers a chunk boundary (0-1, lower = more splits)."""

    window_size: int = 2
    """Number of sentences to combine when computing embeddings for comparison."""

    embedding_batch_size: int = 32
    """Batch size for embedding generation."""


def _tokenize_sentences(text: str) -> list[str]:
    """Tokenize text into sentences using NLTK or fallback."""
    if not text or not text.strip():
        return []
    if _NLTK_AVAILABLE:
        return list(sent_tokenize(text))
    return _fallback_sent_tokenize(text)


def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))


class SemanticChunker:
    """Chunk text by detecting semantic boundaries using embeddings.

    This chunker groups sentences based on semantic similarity rather than
    fixed counts, creating more coherent chunks that preserve topical flow.
    """

    def __init__(
        self,
        embedder: OllamaEmbeddings,
        config: SemanticChunkerConfig | None = None,
    ) -> None:
        """Initialize the semantic chunker.

        Args:
            embedder: Embedding model for computing sentence embeddings.
            config: Chunker configuration. Uses defaults if not provided.
        """
        self._embedder = embedder
        self._config = config or SemanticChunkerConfig()

    @property
    def config(self) -> SemanticChunkerConfig:
        """Return chunker configuration."""
        return self._config

    def _get_window_texts(self, sentences: list[str]) -> list[str]:
        """Create windowed text groups for embedding comparison.

        Combines adjacent sentences into windows for smoother similarity
        computation that's less sensitive to individual sentence noise.
        """
        if len(sentences) <= self._config.window_size:
            return [" ".join(sentences)]

        windows: list[str] = []
        for i in range(len(sentences) - self._config.window_size + 1):
            window = sentences[i : i + self._config.window_size]
            windows.append(" ".join(window))
        return windows

    def _compute_embeddings(self, texts: list[str]) -> np.ndarray:
        """Compute embeddings for a list of texts in batches."""
        if not texts:
            return np.array([])

        all_embeddings: list[list[float]] = []
        batch_size = self._config.embedding_batch_size

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            try:
                batch_embeddings = self._embedder.embed_documents(batch)
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                logger.warning("Failed to embed batch at index %d: %s", i, e)
                # Use zero vectors as fallback to maintain alignment
                dim = len(all_embeddings[0]) if all_embeddings else 384
                all_embeddings.extend([[0.0] * dim for _ in batch])

        return np.array(all_embeddings)

    def _find_breakpoints(
        self,
        sentences: list[str],
        embeddings: np.ndarray,
    ) -> list[int]:
        """Find indices where semantic shifts occur.

        Returns sentence indices after which a chunk boundary should be placed.
        """
        if len(embeddings) < 2:
            return []

        # Compute similarities between adjacent windows
        similarities: list[float] = []
        for i in range(len(embeddings) - 1):
            sim = _cosine_similarity(embeddings[i], embeddings[i + 1])
            similarities.append(sim)

        # Find breakpoints where similarity drops below threshold
        breakpoints: list[int] = []
        current_chunk_size = 0

        for i, sim in enumerate(similarities):
            # Map window index back to sentence index
            # Window i covers sentences [i, i+window_size)
            # A break after window i means break after sentence i+window_size-1
            sentence_idx = i + self._config.window_size - 1
            current_chunk_size += 1

            # Force break at max chunk size
            if current_chunk_size >= self._config.max_chunk_sentences:
                breakpoints.append(sentence_idx)
                current_chunk_size = 0
                continue

            # Check for semantic boundary
            if (
                sim < self._config.similarity_threshold
                and current_chunk_size >= self._config.min_chunk_sentences
            ):
                breakpoints.append(sentence_idx)
                current_chunk_size = 0

        return breakpoints

    def split_text(self, text: str) -> list[str]:
        """Split text into semantically coherent chunks.

        Args:
            text: Input text to chunk.

        Returns:
            List of chunk strings.
        """
        sentences = _tokenize_sentences(text)
        if not sentences:
            return []

        # Handle small documents that don't need chunking
        if len(sentences) <= self._config.min_chunk_sentences:
            return [" ".join(sentences)]

        # Create windows and compute embeddings
        windows = self._get_window_texts(sentences)
        embeddings = self._compute_embeddings(windows)

        if len(embeddings) == 0:
            # Fallback: return as single chunk if embedding fails
            logger.warning(
                "Embedding computation failed, returning single chunk"
            )
            return [" ".join(sentences)]

        # Find semantic breakpoints
        breakpoints = self._find_breakpoints(sentences, embeddings)

        # Create chunks from breakpoints
        chunks: list[str] = []
        start_idx = 0

        for break_idx in breakpoints:
            # break_idx is the last sentence index in the current chunk
            end_idx = break_idx + 1
            if end_idx > start_idx:
                chunk_text = " ".join(sentences[start_idx:end_idx])
                if chunk_text.strip():
                    chunks.append(chunk_text)
            start_idx = end_idx

        # Add remaining sentences as final chunk
        if start_idx < len(sentences):
            final_chunk = " ".join(sentences[start_idx:])
            if final_chunk.strip():
                chunks.append(final_chunk)

        # If no chunks created, return original as single chunk
        if not chunks:
            return [" ".join(sentences)]

        logger.debug(
            "Semantic chunking: %d sentences -> %d chunks",
            len(sentences),
            len(chunks),
        )
        return chunks

    def split_text_with_counts(self, text: str) -> list[tuple[str, int]]:
        """Split text and return (chunk_text, sentence_count) tuples."""
        sentences = _tokenize_sentences(text)
        if not sentences:
            return []

        if len(sentences) <= self._config.min_chunk_sentences:
            return [(" ".join(sentences), len(sentences))]

        windows = self._get_window_texts(sentences)
        embeddings = self._compute_embeddings(windows)

        if len(embeddings) == 0:
            return [(" ".join(sentences), len(sentences))]

        breakpoints = self._find_breakpoints(sentences, embeddings)

        result: list[tuple[str, int]] = []
        start_idx = 0

        for break_idx in breakpoints:
            end_idx = break_idx + 1
            if end_idx > start_idx:
                chunk_sentences = sentences[start_idx:end_idx]
                chunk_text = " ".join(chunk_sentences)
                if chunk_text.strip():
                    result.append((chunk_text, len(chunk_sentences)))
            start_idx = end_idx

        if start_idx < len(sentences):
            final_sentences = sentences[start_idx:]
            final_chunk = " ".join(final_sentences)
            if final_chunk.strip():
                result.append((final_chunk, len(final_sentences)))

        if not result:
            return [(" ".join(sentences), len(sentences))]

        return result

    def split_documents(self, docs: Sequence[Document]) -> list[Document]:
        """Split Documents while preserving metadata.

        Adds 'sentence_count' and 'chunk_index' to each chunk's metadata.
        """
        result: list[Document] = []

        for doc in docs:
            chunks_with_counts = self.split_text_with_counts(doc.page_content)
            for idx, (chunk_text, sentence_count) in enumerate(
                chunks_with_counts
            ):
                metadata = dict(doc.metadata) if doc.metadata else {}
                metadata["sentence_count"] = sentence_count
                metadata["chunk_index"] = idx
                metadata["chunking_mode"] = "semantic"
                result.append(
                    Document(
                        page_content=chunk_text,
                        metadata=metadata,
                    )
                )

        return result

    def __repr__(self) -> str:
        """Return a concise debug representation for semantic chunking config."""
        return (
            f"SemanticChunker("
            f"threshold={self._config.similarity_threshold}, "
            f"min={self._config.min_chunk_sentences}, "
            f"max={self._config.max_chunk_sentences})"
        )
