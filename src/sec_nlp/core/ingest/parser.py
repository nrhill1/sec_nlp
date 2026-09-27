# src/sec_nlp/core/ingest/parser.py
"""HTML parsing and chunking utilities for SEC filings."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from unstructured.documents.elements import Element

    from sec_nlp.core.text.semantic_chunking import (
        SemanticChunker,
    )


import asyncio
import re
from collections.abc import Sequence
from functools import lru_cache
from html.parser import HTMLParser
from importlib.util import find_spec
from pathlib import Path

from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.infra.logger import color_text, logger
from sec_nlp.core.llm.ollama import resolve_ollama_base_url
from sec_nlp.core.text.chunking import SentenceSplitter
from sec_nlp.core.text.filters import (
    SectionFilter,
    create_default_section_filter,
)
from sec_nlp.core.text.keyword import KeywordMatcher, KeywordSpec
from sec_nlp.core.text.section_extractor import SectionExtractor
from sec_nlp.core.text.semantic_settings import SemanticChunkingSettings
from sec_nlp.core.types import as_json_dict
from sec_nlp.types import JsonDict


@lru_cache(maxsize=1)
def _require_local_html_model() -> None:
    """Require a usable local spaCy model before Unstructured can parse HTML.

    Unstructured 0.21.5 installs en_core_web_sm automatically when loading it
    fails. Checking both package presence and local loading first keeps model
    installation outside filing extraction. Successful checks are cached.

    Raises:
        RuntimeError: If the model is absent or cannot be loaded locally.
    """
    if find_spec("en_core_web_sm") is None:
        raise RuntimeError(
            "spaCy model en_core_web_sm is not installed locally; "
            "automatic model downloads are disabled"
        )
    try:
        import spacy

        spacy.load("en_core_web_sm")
    except (ImportError, OSError, ValueError) as exc:
        raise RuntimeError(
            "spaCy model en_core_web_sm could not be loaded locally; "
            "automatic model downloads are disabled"
        ) from exc


class _HTMLTextExtractor(HTMLParser):
    """Collect visible text segments from HTML for offline fallback parsing.

    This extractor intentionally keeps the behavior simple and dependency-free
    so loader code can still operate when `unstructured` cannot initialize its
    NLP stack in offline or sandboxed environments.

    Attributes:
        _segments: Visible text snippets collected from the HTML input.
        _skip_depth: Nesting depth for tags whose contents should be ignored.
    """

    def __init__(self) -> None:
        """Initialize the extractor with empty state."""
        super().__init__(convert_charrefs=True)
        self._segments: list[str] = []
        self._skip_depth = 0

    def handle_starttag(
        self, tag: str, attrs: Sequence[tuple[str, str | None]]
    ) -> None:
        """Track tags whose text content should be skipped."""
        _ = attrs
        if tag.lower() in {"script", "style"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        """Stop skipping text after closing ignored tags."""
        if tag.lower() in {"script", "style"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        """Collect normalized text from visible HTML nodes."""
        if self._skip_depth > 0:
            return
        normalized = " ".join(data.split())
        if normalized:
            self._segments.append(normalized)

    @property
    def segments(self) -> list[str]:
        """Return the collected visible text segments."""
        return list(self._segments)


class HtmlProcessor:
    """Parse and chunk SEC filing HTML content."""

    def __init__(
        self,
        *,
        chunk_size: int,
        chunk_overlap: int,
        section_chunking: bool,
        section_chunk_max_length: int,
        keyword_mode: str,
        semantic_chunking: SemanticChunkingSettings,
    ) -> None:
        """Initialize the parser with chunking and section-extraction settings."""
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.section_chunking = section_chunking
        self.section_chunk_max_length = section_chunk_max_length
        self.keyword_mode = keyword_mode
        self.semantic_chunking = semantic_chunking

        self._splitter = SentenceSplitter(
            chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap
        )
        self._default_section_extractor: SectionExtractor | None = None
        if self.section_chunking:
            default_filter = create_default_section_filter(filter_indices=False)
            self._default_section_extractor = SectionExtractor(
                section_filter=default_filter,
                max_section_length=self.section_chunk_max_length,
                detect_boundaries=True,
            )
        self._semantic_chunker: SemanticChunker | None = (
            self._build_semantic_chunker()
        )

    def _build_semantic_chunker(self) -> SemanticChunker | None:
        """Build semantic chunker when semantic chunking is enabled."""
        if not self.semantic_chunking.enabled:
            return None
        try:
            embedding_base_url = self.semantic_chunking.embedding_base_url
            if embedding_base_url is None:
                embedding_base_url = resolve_ollama_base_url()

            from langchain_ollama.embeddings import OllamaEmbeddings

            embedder = OllamaEmbeddings(
                model=self.semantic_chunking.embedding_model,
                base_url=embedding_base_url,
            )
            from sec_nlp.core.text.semantic_chunking import (
                SemanticChunker,
                SemanticChunkerConfig,
            )

            semantic_config = SemanticChunkerConfig.from_settings(
                self.semantic_chunking
            )
            return SemanticChunker(embedder=embedder, config=semantic_config)
        except Exception as exc:
            logger.warning(
                "Semantic chunker initialization failed; falling back to sentence chunking: %s",
                exc,
            )
            return None

    def _build_section_extractor(
        self, section_filter: SectionFilter | None
    ) -> SectionExtractor | None:
        """Build a section extractor when section chunking is enabled."""
        if not self.section_chunking:
            return None
        if section_filter is None:
            return self._default_section_extractor
        return SectionExtractor(
            section_filter=section_filter,
            max_section_length=self.section_chunk_max_length,
            detect_boundaries=True,
        )

    def _section_log_suffix(self, section_chunks: list[Document]) -> str:
        """Build a log suffix describing section-extraction mode."""
        meta = section_chunks[0].metadata or {}
        symbol_value = meta.get("symbol") or meta.get("ticker")
        symbol = (
            symbol_value.strip().upper()
            if isinstance(symbol_value, str) and symbol_value.strip()
            else None
        )
        accession_value = meta.get("accession_number") or meta.get("accession")
        if isinstance(accession_value, str):
            accession = accession_value.strip()
        else:
            accession = None
        if not symbol or not accession:
            source = meta.get("source") or meta.get("file_path")
            if isinstance(source, str):
                match = re.search(
                    r"/sec-edgar-filings/([^/]+)/[^/]+/([^/]+)/", source
                )
                if match:
                    if not symbol:
                        symbol = match.group(1)
                    if not accession:
                        accession = match.group(2)
        symbol = symbol or "unknown"
        accession = accession or "unknown"
        return color_text(f"{symbol}/{accession}", color="dim")

    def _log_section_chunk_summary(
        self, section_chunks: list[Document]
    ) -> None:
        """Log section and chunk statistics for parsed documents."""
        if not section_chunks:
            return

        suffix = self._section_log_suffix(section_chunks)
        section_counts: dict[str, int] = {}
        for chunk in section_chunks:
            meta = chunk.metadata or {}
            section_type = str(meta.get("section_type") or "").strip()
            section_number = str(meta.get("section_number") or "").strip()
            if section_type and section_number:
                key = f"{section_type.title()} {section_number}"
            elif section_number:
                key = section_number
            elif section_type:
                key = section_type.title()
            else:
                key = "Unknown"
            section_counts[key] = section_counts.get(key, 0) + 1

        section_total = len(section_counts)
        if section_total == 0:
            return

        def sort_key(item: tuple[str, int]) -> tuple[int, str]:
            name = item[0].lower()
            if name.startswith("item "):
                return (0, name[5:])
            if name.startswith("part "):
                return (1, name[5:])
            if name.startswith("exhibit "):
                return (2, name[8:])
            return (3, name)

        entries = []
        for section, count in sorted(section_counts.items(), key=sort_key):
            entries.append(
                f"{color_text(section, color='blue')}"
                f"{color_text(':', color='dim')} "
                f"{color_text(str(count), color='yellow')}"
            )

        header = (
            f"{color_text('Sections', color='green')}: "
            f"{color_text(str(section_total), color='yellow')} "
            f"{color_text('(chunks per section)', color='dim')}"
        )
        logger.info("%s %s", header, suffix)

        per_line = 4
        separator = color_text(" | ", color="dim")
        for i in range(0, len(entries), per_line):
            group = entries[i : i + per_line]
            line = (
                f"{color_text('{', color='dim')} "
                + separator.join(group)
                + f" {color_text('}', color='dim')}"
            )
            logger.info("%s %s", line, suffix)

    def _chunk_text(
        self,
        text_content: str,
        metadata: JsonDict | None,
        section_filter: SectionFilter | None,
        keywords: list[str] | None = None,
    ) -> list[Document]:
        """Chunk long text into bounded segments for downstream processing."""
        if not text_content or not text_content.strip():
            return []

        base_meta = dict(metadata) if metadata else {}
        extractor = self._build_section_extractor(section_filter)
        if extractor:
            try:
                section_chunks = extractor.extract_and_chunk(
                    text_content,
                    metadata=base_meta,
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap,
                )
            except Exception as exc:
                logger.warning("Section chunking failed: %s", exc)
                section_chunks = []
            if section_chunks:
                if keywords:
                    section_chunks = self._filter_documents_by_keywords(
                        section_chunks,
                        keywords,
                    )
                    if not section_chunks:
                        logger.debug(
                            "No section chunks matched keywords: %s",
                            keywords,
                        )
                        return []
                self._log_section_chunk_summary(section_chunks)
                if self._semantic_chunker is not None:
                    return self._semantic_chunk_documents(section_chunks)
                return section_chunks

        doc = Document(page_content=text_content, metadata=base_meta)
        if self._semantic_chunker is not None:
            semantic_chunks = self._semantic_chunk_documents([doc])
            if section_filter:
                return list(section_filter.filter_documents(semantic_chunks))
            return semantic_chunks
        chunk_list = self._splitter.split_documents([doc])
        if section_filter:
            return list(section_filter.filter_documents(chunk_list))
        return chunk_list

    def _semantic_chunk_documents(self, docs: list[Document]) -> list[Document]:
        """Split documents with semantic chunking while preserving metadata."""
        semantic_chunker = self._semantic_chunker
        if semantic_chunker is None:
            return docs

        chunked_docs: list[Document] = []
        for doc in docs:
            base_meta = dict(doc.metadata) if doc.metadata else {}
            try:
                semantic_chunks = semantic_chunker.split_documents([doc])
            except Exception as exc:
                logger.warning(
                    "Semantic chunking failed; preserving original chunk: %s",
                    exc,
                )
                semantic_chunks = [doc]
            for chunk in semantic_chunks:
                chunk_metadata = dict(chunk.metadata) if chunk.metadata else {}
                merged_metadata = dict(base_meta)
                merged_metadata.update(chunk_metadata)
                chunked_docs.append(
                    Document(
                        page_content=chunk.page_content,
                        metadata=merged_metadata,
                    )
                )
        return chunked_docs

    def _filter_elements_by_keywords(
        self,
        elements: list[Element],
        keywords: list[str],
    ) -> list[Element]:
        """Filter parsed filing elements by keyword matches."""
        if not keywords:
            return elements
        specs = [
            KeywordSpec(pattern=kw, priority=1, weight=1.0) for kw in keywords
        ]

        filtered: list[Element] = []
        for element in elements:
            element_text = str(element)
            score = KeywordMatcher.score_keywords(
                element_text,
                specs,
                case_insensitive=True,
            )

            if (
                self.keyword_mode == "any"
                and score.hits
                or self.keyword_mode == "all"
                and len(score.hits) == len(specs)
            ):
                filtered.append(element)

        return filtered

    def _filter_documents_by_keywords(
        self,
        documents: list[Document],
        keywords: list[str],
    ) -> list[Document]:
        """Filter parsed documents by keyword relevance."""
        if not keywords:
            return documents
        specs = [
            KeywordSpec(pattern=kw, priority=1, weight=1.0) for kw in keywords
        ]

        filtered = []
        for doc in documents:
            score = KeywordMatcher.score_keywords(
                doc.page_content,
                specs,
                case_insensitive=True,
            )
            if (
                self.keyword_mode == "any"
                and score.hits
                or self.keyword_mode == "all"
                and len(score.hits) == len(specs)
            ):
                filtered.append(doc)

        return filtered

    @staticmethod
    def _should_fallback_to_plain_text(exc: BaseException) -> bool:
        """Return whether a parser failure should use local plain-text fallback."""
        message = str(exc).lower()
        exception_name = exc.__class__.__name__.lower()
        fallback_markers = (
            "spacy",
            "en_core_web_sm",
            "failed to download",
            "can't find model",
            "cannot find model",
            "socket.socket",
            "socketblockederror",
        )
        return any(marker in message for marker in fallback_markers) or any(
            marker in exception_name for marker in fallback_markers
        )

    @staticmethod
    def _extract_text_segments(html: str) -> list[str]:
        """Extract visible text segments from raw HTML with stdlib parsing."""
        extractor = _HTMLTextExtractor()
        extractor.feed(html)
        extractor.close()
        return extractor.segments

    def _filter_text_segments_by_keywords(
        self,
        segments: list[str],
        keywords: list[str],
    ) -> list[str]:
        """Filter plain-text segments by keyword relevance."""
        if not keywords:
            return segments
        specs = [
            KeywordSpec(pattern=kw, priority=1, weight=1.0) for kw in keywords
        ]

        filtered: list[str] = []
        for segment in segments:
            score = KeywordMatcher.score_keywords(
                segment,
                specs,
                case_insensitive=True,
            )
            if (
                self.keyword_mode == "any"
                and score.hits
                or self.keyword_mode == "all"
                and len(score.hits) == len(specs)
            ):
                filtered.append(segment)

        return filtered

    def _fallback_transform_html(
        self,
        html: str,
        *,
        metadata: JsonDict,
        keywords: list[str] | None,
        section_filter: SectionFilter | None,
    ) -> list[Document]:
        """Transform HTML using dependency-free plain-text extraction."""
        text_segments = self._extract_text_segments(html)
        defer_keyword_filter = (
            keywords is not None
            and section_filter is not None
            and self.section_chunking
        )
        if keywords and not defer_keyword_filter:
            text_segments = self._filter_text_segments_by_keywords(
                text_segments,
                keywords,
            )
            if not text_segments:
                return []

        text_content = " ".join(text_segments)
        return self._chunk_text(
            text_content,
            metadata,
            section_filter,
            keywords if defer_keyword_filter else None,
        )

    def transform_html(
        self,
        html_path: Path,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> Sequence[Document]:
        if not html_path.exists():
            raise FileNotFoundError(str(html_path))
        try:
            _require_local_html_model()
            from unstructured.partition.html import partition_html

            elements = partition_html(filename=str(html_path))
            docs = [
                Document(
                    page_content=str(element),
                    metadata={
                        **(as_json_dict(element.metadata.to_dict()) or {}),
                        "category": element.category,
                        "element_id": element.id,
                    },
                )
                for element in elements
            ]
        except RuntimeError as exc:
            if not self._should_fallback_to_plain_text(exc):
                raise
            logger.warning(
                "HTML parsing fell back to plain-text extraction for %s: %s",
                html_path.name,
                exc,
            )
            return self._fallback_transform_html(
                html_path.read_text(encoding="utf-8", errors="ignore"),
                metadata={
                    "source": str(html_path),
                    "file_path": str(html_path),
                },
                keywords=keywords,
                section_filter=section_filter,
            )

        defer_keyword_filter = (
            keywords is not None
            and section_filter is not None
            and self.section_chunking
        )
        if keywords and not defer_keyword_filter:
            docs = self._filter_documents_by_keywords(docs, keywords)
            if not docs:
                return []

        if section_filter and not self.section_chunking:
            docs = section_filter.filter_documents(docs)
            if not docs:
                return []

        text_content = " ".join(
            doc.page_content for doc in docs if doc.page_content
        )
        base_meta = dict(docs[0].metadata) if docs else {}
        base_meta["source"] = str(html_path)
        base_meta["file_path"] = str(html_path)
        return self._chunk_text(
            text_content,
            base_meta,
            section_filter,
            keywords if defer_keyword_filter else None,
        )

    def transform_html_string(
        self,
        html: str,
        metadata: dict[str, str | int | float] | None = None,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> Sequence[Document]:
        try:
            _require_local_html_model()
            from unstructured.partition.html import partition_html

            elements = partition_html(text=html)
        except RuntimeError as exc:
            if not self._should_fallback_to_plain_text(exc):
                raise
            logger.warning(
                "HTML string parsing fell back to plain-text extraction: %s",
                exc,
            )
            return self._fallback_transform_html(
                html,
                metadata=dict(metadata) if metadata else {},
                keywords=keywords,
                section_filter=section_filter,
            )

        defer_keyword_filter = (
            keywords is not None
            and section_filter is not None
            and self.section_chunking
        )
        if keywords and not defer_keyword_filter:
            elements = self._filter_elements_by_keywords(elements, keywords)
            if not elements:
                logger.debug("No elements matched keywords: %s", keywords)
                return []

        text_content = " ".join([str(el) for el in elements])

        return self._chunk_text(
            text_content,
            dict(metadata) if metadata else {},
            section_filter,
            keywords if defer_keyword_filter else None,
        )

    async def transform_html_async(
        self,
        html_path: Path,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> Sequence[Document]:
        return await asyncio.to_thread(
            self.transform_html,
            html_path,
            keywords,
            section_filter,
        )
