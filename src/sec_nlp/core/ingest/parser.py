# src/sec_nlp/core/ingest/parser.py
"""HTML parsing and chunking utilities for SEC filings."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from pathlib import Path

from langchain_community.document_loaders import UnstructuredHTMLLoader
from langchain_core.documents import Document
from unstructured.documents.elements import Element
from unstructured.partition.html import partition_html

from sec_nlp.core.infra.logger import color_text, logger
from sec_nlp.core.text.chunking import SentenceSplitter
from sec_nlp.core.text.filters import (
    SectionFilter,
    create_default_section_filter,
)
from sec_nlp.core.text.keyword import KeywordMatcher, KeywordSpec
from sec_nlp.core.text.section_extractor import SectionExtractor
from sec_nlp.types import JsonDict


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
    ) -> None:
        """Initialize the parser with chunking and section-extraction settings."""
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.section_chunking = section_chunking
        self.section_chunk_max_length = section_chunk_max_length
        self.keyword_mode = keyword_mode

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
                f"{color_text(section, color='cyan')}"
                f"{color_text(':', color='dim')} "
                f"{color_text(str(count), color='magenta')}"
            )

        header = (
            f"{color_text('Sections', color='green')}: "
            f"{color_text(str(section_total), color='magenta')} "
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
                self._log_section_chunk_summary(section_chunks)
                return section_chunks

        doc = Document(page_content=text_content, metadata=base_meta)
        chunk_list = self._splitter.split_documents([doc])
        if section_filter:
            return list(section_filter.filter_documents(chunk_list))
        return chunk_list

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

    def transform_html(
        self,
        html_path: Path,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> Sequence[Document]:
        if not html_path.exists():
            raise FileNotFoundError(str(html_path))
        loader = UnstructuredHTMLLoader(
            file_path=str(html_path), mode="elements"
        )
        docs = loader.load()

        if keywords:
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
        base_meta.setdefault("source", str(html_path))
        base_meta.setdefault("file_path", str(html_path))
        return self._chunk_text(text_content, base_meta, section_filter)

    def transform_html_string(
        self,
        html: str,
        metadata: dict[str, str | int | float] | None = None,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> Sequence[Document]:
        elements = partition_html(text=html)

        if keywords:
            elements = self._filter_elements_by_keywords(elements, keywords)
            if not elements:
                logger.debug("No elements matched keywords: %s", keywords)
                return []

        text_content = " ".join([str(el) for el in elements])

        return self._chunk_text(
            text_content, dict(metadata) if metadata else {}, section_filter
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
