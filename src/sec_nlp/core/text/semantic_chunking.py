# src/sec_nlp/core/text/semantic_chunking.py
"""Semantic chunking adapter built on LangChain experimental SemanticChunker.

This module keeps a stable local chunker interface used by analyze preprocessing
while delegating boundary detection to LangChain's experimental splitter.
Local post-processing still enforces sentence-count bounds so existing pipeline
controls remain meaningful.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from inspect import Parameter, Signature, signature
from typing import Literal

from langchain_core.documents import Document as LangChainDocument
from langchain_core.embeddings import Embeddings

from sec_nlp.adapters.documents import from_langchain
from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.text.chunking import _fallback_sent_tokenize
from sec_nlp.core.text.semantic_settings import SemanticChunkingSettings
from sec_nlp.types import JsonValue

type ChunkMetadata = dict[str, JsonValue]
type CreateDocumentsFn = Callable[
    [list[str], list[ChunkMetadata] | None], list[Document]
]
_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]")


@dataclass(frozen=True)
class SemanticChunkerConfig:
    """Store semantic chunking controls used by analyze preprocessing."""

    min_chunk_sentences: int = 3
    """Minimum sentences per chunk after post-processing."""

    max_chunk_sentences: int = 50
    """Maximum sentences per chunk after post-processing."""

    similarity_threshold: float = 0.5
    """Boundary aggressiveness mapped to experimental threshold amount."""

    window_size: int = 2
    """Context window hint mapped to experimental buffer size when available."""

    breakpoint_threshold_type: Literal[
        "percentile",
        "standard_deviation",
        "interquartile",
        "gradient",
    ] = "percentile"
    """Experimental threshold strategy used to place semantic breakpoints."""

    breakpoint_threshold_amount: float | None = None
    """Optional explicit threshold amount for the selected strategy."""

    number_of_chunks: int | None = None
    """Optional target number of chunks passed through to experimental splitter."""

    sentence_split_regex: str = r"(?<=[.?!])\s+"
    """Regex pattern used for sentence splitting in chunk post-processing."""

    min_chunk_size: int | None = None
    """Optional minimum chunk size in characters for experimental splitter."""

    add_start_index: bool = False
    """When true, include start offsets in splitter metadata."""

    max_chunk_tokens: int | None = 384
    """Optional approximate maximum tokens per chunk after post-processing."""

    embedding_batch_size: int = 32
    """Unused compatibility field retained for stable config shape."""

    @classmethod
    def from_settings(
        cls, settings: SemanticChunkingSettings
    ) -> SemanticChunkerConfig:
        """Build runtime chunker config from shared semantic settings."""
        return cls(
            min_chunk_sentences=settings.min_chunk_sentences,
            max_chunk_sentences=settings.max_chunk_sentences,
            similarity_threshold=settings.similarity_threshold,
            window_size=settings.buffer_size,
            breakpoint_threshold_type=settings.breakpoint_threshold_type,
            breakpoint_threshold_amount=settings.breakpoint_threshold_amount,
            number_of_chunks=settings.number_of_chunks,
            sentence_split_regex=settings.sentence_split_regex,
            min_chunk_size=settings.min_chunk_size,
            add_start_index=settings.add_start_index,
            max_chunk_tokens=settings.max_chunk_tokens,
        )


def _tokenize_sentences(text: str, sentence_split_regex: str) -> list[str]:
    """Tokenize text into sentences using the configured regex."""
    if not text or not text.strip():
        return []
    regex_sentences = [
        sentence.strip()
        for sentence in re.split(sentence_split_regex, text)
        if sentence.strip()
    ]
    if regex_sentences:
        return regex_sentences
    return _fallback_sent_tokenize(text)


def _estimate_token_count(text: str) -> int:
    """Return a tokenizer-free approximate token count for one chunk."""
    stripped = text.strip()
    if not stripped:
        return 0
    return len(_TOKEN_PATTERN.findall(stripped))


def _load_experimental_chunker() -> type:
    """Load LangChain experimental SemanticChunker."""
    try:
        from langchain_experimental.text_splitter import (
            SemanticChunker as ExperimentalSemanticChunker,
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Semantic chunking requires 'langchain-experimental'. "
            "Install it before running analyze with chunking_mode='semantic'."
        ) from exc
    return ExperimentalSemanticChunker


def _signature_accepts(signature_obj: Signature, name: str) -> bool:
    """Return whether a callable signature accepts a named parameter."""
    param = signature_obj.parameters.get(name)
    return isinstance(param, Parameter)


class SemanticChunker:
    """Split text with LangChain semantic chunking plus local sentence bounds."""

    def __init__(
        self,
        embedder: Embeddings,
        config: SemanticChunkerConfig | None = None,
    ) -> None:
        """Initialize the semantic chunker adapter.

        Args:
            embedder: Embeddings backend passed to experimental chunker.
            config: Optional local chunking controls.
        """
        self._embedder = embedder
        self._config = config or SemanticChunkerConfig()
        self._create_documents_fn = self._build_create_documents_fn()

    @property
    def config(self) -> SemanticChunkerConfig:
        """Return chunker configuration."""
        return self._config

    def _build_create_documents_fn(self) -> CreateDocumentsFn:
        """Build and wrap the experimental splitter's create-documents callable."""
        splitter_cls = _load_experimental_chunker()
        init_signature = signature(splitter_cls.__init__)
        splitter_kwargs: dict[str, bool | int | float | str] = {}

        if _signature_accepts(init_signature, "breakpoint_threshold_type"):
            splitter_kwargs["breakpoint_threshold_type"] = (
                self._config.breakpoint_threshold_type
            )
        if _signature_accepts(init_signature, "breakpoint_threshold_amount"):
            threshold_amount = self._config.breakpoint_threshold_amount
            if threshold_amount is None:
                threshold_amount = self._config.similarity_threshold * 100.0
            if self._config.breakpoint_threshold_type == "percentile":
                threshold_amount = max(0.0, min(100.0, threshold_amount))
            else:
                threshold_amount = max(0.0, threshold_amount)
            splitter_kwargs["breakpoint_threshold_amount"] = float(
                threshold_amount
            )
        if _signature_accepts(init_signature, "buffer_size"):
            splitter_kwargs["buffer_size"] = max(1, self._config.window_size)
        if _signature_accepts(init_signature, "add_start_index"):
            splitter_kwargs["add_start_index"] = self._config.add_start_index
        if (
            _signature_accepts(init_signature, "number_of_chunks")
            and self._config.number_of_chunks is not None
        ):
            splitter_kwargs["number_of_chunks"] = max(
                1, self._config.number_of_chunks
            )
        if _signature_accepts(init_signature, "sentence_split_regex"):
            splitter_kwargs["sentence_split_regex"] = (
                self._config.sentence_split_regex
            )
        if (
            _signature_accepts(init_signature, "min_chunk_size")
            and self._config.min_chunk_size is not None
        ):
            splitter_kwargs["min_chunk_size"] = max(
                1, self._config.min_chunk_size
            )

        splitter = splitter_cls(self._embedder, **splitter_kwargs)
        create_documents = splitter.create_documents
        call_signature = signature(create_documents)
        supports_metadata = _signature_accepts(call_signature, "metadatas")

        def _invoke(
            texts: list[str],
            metadatas: list[ChunkMetadata] | None,
        ) -> list[Document]:
            if supports_metadata and metadatas is not None:
                raw_documents = create_documents(texts, metadatas=metadatas)
            else:
                raw_documents = create_documents(texts)
            return self._coerce_documents(raw_documents)

        return _invoke

    @staticmethod
    def _coerce_documents(
        raw_documents: Sequence[Document | LangChainDocument],
    ) -> list[Document]:
        """Validate that the splitter returned LangChain Document instances."""
        result: list[Document] = []
        for doc in raw_documents:
            if not isinstance(doc, (Document, LangChainDocument)):
                raise TypeError(
                    "Experimental SemanticChunker returned non-Document value"
                )
            result.append(from_langchain(doc))
        return result

    def _create_documents(
        self,
        *,
        texts: list[str],
        metadatas: list[ChunkMetadata] | None = None,
    ) -> list[Document]:
        """Create chunks using the wrapped experimental splitter."""
        return self._create_documents_fn(texts, metadatas)

    def _normalize_sentence_groups(
        self, groups: list[list[str]]
    ) -> list[list[str]]:
        """Enforce max/min sentence constraints across sequential groups."""
        if not groups:
            return []

        max_sentences = max(1, self._config.max_chunk_sentences)
        min_sentences = max(1, self._config.min_chunk_sentences)
        max_tokens = self._config.max_chunk_tokens

        split_groups: list[list[str]] = []
        for group in groups:
            current_group: list[str] = []
            current_tokens = 0
            for sentence in group:
                sentence_tokens = _estimate_token_count(sentence)
                reached_sentence_limit = len(current_group) >= max_sentences
                reached_token_limit = (
                    max_tokens is not None
                    and current_group
                    and current_tokens + sentence_tokens > max_tokens
                )
                if reached_sentence_limit or reached_token_limit:
                    split_groups.append(current_group)
                    current_group = [sentence]
                    current_tokens = sentence_tokens
                    continue
                current_group.append(sentence)
                current_tokens += sentence_tokens
            if current_group:
                split_groups.append(current_group)

        merged_groups: list[list[str]] = []
        for group in split_groups:
            if (
                merged_groups
                and len(group) < min_sentences
                and (len(merged_groups[-1]) + len(group) <= max_sentences)
            ):
                merged_tokens = _estimate_token_count(
                    " ".join(merged_groups[-1])
                ) + _estimate_token_count(" ".join(group))
                if max_tokens is not None and merged_tokens > max_tokens:
                    merged_groups.append(list(group))
                    continue
                merged_groups[-1].extend(group)
                continue
            merged_groups.append(list(group))

        if len(merged_groups) >= 2 and len(merged_groups[-1]) < min_sentences:
            trailing = merged_groups[-1]
            prior_group = merged_groups[-2]
            if len(prior_group) + len(trailing) <= max_sentences:
                merged_tokens = _estimate_token_count(
                    " ".join(prior_group)
                ) + _estimate_token_count(" ".join(trailing))
                if max_tokens is None or merged_tokens <= max_tokens:
                    merged_groups.pop()
                    prior_group.extend(trailing)

        return [group for group in merged_groups if group]

    def split_text_with_counts(self, text: str) -> list[tuple[str, int]]:
        """Split text into semantic chunks with sentence counts."""
        stripped = text.strip()
        if not stripped:
            return []

        docs = self._create_documents(texts=[stripped], metadatas=None)
        sentence_groups: list[list[str]] = []
        for doc in docs:
            sentences = _tokenize_sentences(
                doc.page_content,
                self._config.sentence_split_regex,
            )
            if sentences:
                sentence_groups.append(sentences)

        if not sentence_groups:
            fallback = _tokenize_sentences(
                stripped,
                self._config.sentence_split_regex,
            )
            if not fallback:
                return []
            sentence_groups = [fallback]

        normalized = self._normalize_sentence_groups(sentence_groups)
        return [(" ".join(group), len(group)) for group in normalized]

    def split_text(self, text: str) -> list[str]:
        """Split text into semantically coherent chunks."""
        return [
            chunk_text
            for chunk_text, _sentence_count in self.split_text_with_counts(text)
        ]

    def split_documents(self, docs: Sequence[Document]) -> list[Document]:
        """Split documents into semantic chunks while preserving metadata."""
        result: list[Document] = []
        for doc in docs:
            base_metadata = (
                dict(doc.metadata) if isinstance(doc.metadata, dict) else {}
            )
            chunks_with_counts = self.split_text_with_counts(doc.page_content)
            for chunk_index, (chunk_text, sentence_count) in enumerate(
                chunks_with_counts
            ):
                metadata = dict(base_metadata)
                metadata["sentence_count"] = sentence_count
                metadata["token_count"] = _estimate_token_count(chunk_text)
                metadata["chunk_index"] = chunk_index
                metadata["chunking_mode"] = "semantic"
                result.append(
                    Document(
                        page_content=chunk_text,
                        metadata=metadata,
                    )
                )

        logger.debug(
            "Semantic chunking: %d documents -> %d chunks",
            len(docs),
            len(result),
        )
        return result

    def __repr__(self) -> str:
        """Return a concise debug representation for semantic chunking config."""
        return (
            "SemanticChunker("
            f"threshold={self._config.similarity_threshold}, "
            f"min={self._config.min_chunk_sentences}, "
            f"max={self._config.max_chunk_sentences}, "
            f"max_tokens={self._config.max_chunk_tokens})"
        )
