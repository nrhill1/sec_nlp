# src/sec_nlp/core/text/chunking.py
"""Sentence-based chunking using NLTK sentence tokenization.

Chunk size and overlap are measured in **sentences**, not characters.
This preserves natural language boundaries for better context in downstream tasks.

Example:
    splitter = SentenceSplitter(chunk_size=10, chunk_overlap=2)
    # Creates chunks of up to 10 sentences with 2-sentence overlap
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Sequence
from importlib import import_module
from pathlib import Path

from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.infra.settings import CACHE_DIR

# Tokenizer data is optional and never downloaded or created during import.
NLTK_DATA_DIR = Path(os.environ.get("NLTK_DATA", str(CACHE_DIR / "nltk_data")))
_NLTK_AVAILABLE = False
_SENT_TOKENIZE: Callable[[str], list[str]] | None = None


_TOKENIZER_CHECKED = False


def _load_tokenizer() -> None:
    """Use installed sentence data lazily, without downloading model files."""
    global _TOKENIZER_CHECKED, _NLTK_AVAILABLE, _SENT_TOKENIZE
    if _TOKENIZER_CHECKED:
        return
    _TOKENIZER_CHECKED = True
    try:
        nltk = import_module("nltk")
        sent_tokenize = import_module("nltk.tokenize").sent_tokenize

        if str(NLTK_DATA_DIR) not in nltk.data.path:
            nltk.data.path.insert(0, str(NLTK_DATA_DIR))
        sent_tokenize("A sentence. Another sentence.")
    except (ImportError, LookupError, OSError, AttributeError):
        logger.debug(
            "Installed sentence tokenizer unavailable; using local fallback",
            exc_info=True,
        )
        return
    _SENT_TOKENIZE = sent_tokenize
    _NLTK_AVAILABLE = True


def _fallback_sent_tokenize(text: str) -> list[str]:
    """Fallback sentence tokenizer when NLTK is unavailable."""
    # Split on sentence-ending punctuation followed by space or newline
    pattern = r"(?<=[.!?])\s+"
    sentences = re.split(pattern, text)
    return [s.strip() for s in sentences if s.strip()]


def count_sentences(text: str) -> int:
    """Count sentences in text using the available tokenizer."""
    if not text or not text.strip():
        return 0
    _load_tokenizer()
    if _NLTK_AVAILABLE and _SENT_TOKENIZE is not None:
        return len(_SENT_TOKENIZE(text))
    return len(_fallback_sent_tokenize(text))


class SentenceSplitter:
    """Chunk text by grouping sentences.

    Unlike character-based splitters, this preserves sentence boundaries.
    The chunk_size parameter specifies **max sentences per chunk** (not characters).
    """

    def __init__(
        self,
        *,
        chunk_size: int = 10,
        chunk_overlap: int = 2,
    ) -> None:
        """Initialize the sentence-based splitter.

        Args:
            chunk_size: Maximum number of **sentences** per chunk (not characters).
            chunk_overlap: Number of **sentences** to overlap between chunks.
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")

        self._max_sentences = chunk_size
        self._overlap_sentences = chunk_overlap

    @property
    def max_sentences(self) -> int:
        """Maximum sentences per chunk."""
        return self._max_sentences

    @property
    def overlap_sentences(self) -> int:
        """Sentence overlap between chunks."""
        return self._overlap_sentences

    def _tokenize_sentences(self, text: str) -> list[str]:
        """Tokenize text into sentences."""
        if not text or not text.strip():
            return []

        _load_tokenizer()
        if _NLTK_AVAILABLE and _SENT_TOKENIZE is not None:
            return list(_SENT_TOKENIZE(text))
        return _fallback_sent_tokenize(text)

    def split_text(self, text: str) -> list[str]:
        """Split raw text into sentence-based chunks."""
        sentences = self._tokenize_sentences(text)
        if not sentences:
            return []

        chunks: list[str] = []
        step = self._max_sentences - self._overlap_sentences
        if step <= 0:
            step = 1

        i = 0
        while i < len(sentences):
            chunk_sentences = sentences[i : i + self._max_sentences]
            chunk_text = " ".join(chunk_sentences)
            if chunk_text.strip():
                chunks.append(chunk_text)
            i += step

        return chunks

    def split_text_with_counts(self, text: str) -> list[tuple[str, int]]:
        """Split text and return (chunk_text, sentence_count) tuples."""
        sentences = self._tokenize_sentences(text)
        if not sentences:
            return []

        result: list[tuple[str, int]] = []
        step = self._max_sentences - self._overlap_sentences
        if step <= 0:
            step = 1

        i = 0
        while i < len(sentences):
            chunk_sentences = sentences[i : i + self._max_sentences]
            chunk_text = " ".join(chunk_sentences)
            if chunk_text.strip():
                result.append((chunk_text, len(chunk_sentences)))
            i += step

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
                result.append(
                    Document(
                        page_content=chunk_text,
                        metadata=metadata,
                    )
                )
        return result

    def __repr__(self) -> str:
        """Return a concise debug representation for chunking config."""
        tokenizer = "NLTK" if _NLTK_AVAILABLE else "regex-fallback"
        return (
            f"SentenceSplitter(max_sentences={self._max_sentences}, "
            f"overlap={self._overlap_sentences}, tokenizer={tokenizer})"
        )
