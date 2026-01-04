# src/sec_nlp/pipelines/presets/analyze/preprocess.py
"""Chunking and preprocessing for the analyze pipeline."""

from __future__ import annotations

from collections.abc import Iterable

from langchain_core.documents import Document

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.text.chunking import SentenceSplitter
from sec_nlp.core.text.deduplication import SimHashConfig, SimHashDeduplicator
from sec_nlp.core.text.keyword import KeywordMatcher
from sec_nlp.core.text.section_extractor import SectionExtractor
from sec_nlp.pipelines.chunk_filters import limit_docs_per_accession

from .config import AnalyzeConfig
from .topic_scoring import (
    build_topic_matcher,
    normalize_topics,
    score_documents,
)


class ChunkPreprocessor:
    """Split documents into chunks and apply configurable filters."""

    def __init__(
        self,
        *,
        config: AnalyzeConfig,
        section_extractor: SectionExtractor | None = None,
        topics: Iterable[str] | None = None,
        topic_matcher: KeywordMatcher | None = None,
        min_topic_hits: int = 0,
        prioritize_topics: bool = True,
    ) -> None:
        self.config = config
        self.section_extractor = section_extractor
        self.topics = normalize_topics(topics)
        self.topic_matcher = topic_matcher or build_topic_matcher(self.topics)
        self.min_topic_hits = min_topic_hits
        self.prioritize_topics = prioritize_topics

    def chunk_and_prepare(self, docs: list[Document]) -> list[Document]:
        """Split into chunks (if needed) then apply filters."""
        if not docs:
            return []
        if self._docs_are_chunked(docs):
            return self.prepare_documents(docs)
        chunks = self.split_into_chunks(docs)
        if not chunks:
            return []
        return self.prepare_documents(chunks)

    @staticmethod
    def _docs_are_chunked(docs: list[Document]) -> bool:
        """Heuristic: detect whether documents already represent chunks."""
        for doc in docs:
            meta = doc.metadata or {}
            if "sentence_count" in meta or "chunk_index" in meta:
                return True
        return False

    def split_into_chunks(self, docs: list[Document]) -> list[Document]:
        """Split documents into chunks, preserving section metadata."""
        chunks: list[Document] = []

        if self.section_extractor:
            for doc in docs:
                metadata = doc.metadata or {}
                section_chunks = self.section_extractor.extract_and_chunk(
                    doc.page_content or "",
                    metadata=metadata,
                    chunk_size=self.config.chunk_size,
                    chunk_overlap=self.config.chunk_overlap,
                )
                chunks.extend(section_chunks)
        else:
            splitter = SentenceSplitter(
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap,
            )
            for doc in docs:
                base_meta = doc.metadata or {}
                for idx, chunk in enumerate(splitter.split_documents([doc])):
                    chunk.metadata = {
                        **(chunk.metadata or {}),
                        **base_meta,
                        "chunk_index": idx,
                        "section_number": base_meta.get("section_number", ""),
                    }
                    chunks.append(chunk)

        return chunks

    def prepare_documents(self, docs: list[Document]) -> list[Document]:
        """Apply configured filters to chunked documents."""
        start_total = len(docs)
        filtered: list[Document] = []
        effective_top_k: int | None = None

        for doc in docs:
            content = (doc.page_content or "").strip()

            if self.config.skip_empty_sections and not content:
                continue

            if len(content) < self.config.min_chunk_length:
                continue
            if (
                self.config.max_chunk_length
                and len(content) > self.config.max_chunk_length
            ):
                continue

            filtered.append(doc)

        if len(filtered) != start_total:
            max_display = (
                self.config.max_chunk_length
                if self.config.max_chunk_length is not None
                else "inf"
            )
            logger.info(
                "Chunk length filter: kept %d/%d (min=%d, max=%s)",
                len(filtered),
                start_total,
                self.config.min_chunk_length,
                max_display,
            )

        if self.topics and filtered:
            filtered = score_documents(
                filtered,
                topics=self.topics,
                matcher=self.topic_matcher,
                min_hits=self.min_topic_hits,
                prioritize=self.prioritize_topics,
            )

        if self.config.deduplicate_chunks and filtered:
            filtered = self._deduplicate_documents_simhash(filtered)

        if self.config.max_chunks_per_filing and filtered:
            (
                filtered,
                kept_counts,
                skipped_counts,
            ) = limit_docs_per_accession(
                filtered, self.config.max_chunks_per_filing
            )
            for accession, skipped in skipped_counts.items():
                if skipped > 0:
                    kept = kept_counts.get(accession, 0)
                    logger.info(
                        "Per-filing cap: %d -> %d chunks for %s",
                        kept + skipped,
                        kept,
                        accession,
                    )

        if filtered:
            effective_top_k = self.config.top_k_chunks
            if self.config.adaptive_top_k_cap and (
                effective_top_k is None
                or effective_top_k > self.config.adaptive_top_k_cap
            ):
                effective_top_k = self.config.adaptive_top_k_cap

        if effective_top_k and filtered:
            before = len(filtered)
            filtered = self._apply_top_k(filtered, effective_top_k)
            logger.info(
                "Top-K filter: kept %d/%d (k=%d)",
                len(filtered),
                before,
                effective_top_k,
            )

        return filtered

    def _deduplicate_documents_simhash(
        self, docs: list[Document]
    ) -> list[Document]:
        """SimHash-based deduplication using indexed lookups."""
        local_deduper = SimHashDeduplicator(
            config=SimHashConfig(
                num_bits=self.config.simhash_bits,
                max_distance=self.config.simhash_max_distance,
            )
        )
        return local_deduper.deduplicate_documents(docs)

    @staticmethod
    def _apply_top_k(docs: list[Document], k: int) -> list[Document]:
        """Keep the top-K documents by topic score (fallback to length)."""
        scored: list[tuple[Document, int]] = []
        for doc in docs:
            meta = doc.metadata or {}
            score = meta.get("topic_score")
            if score is None:
                score = len((doc.page_content or "").strip())
            scored.append((doc, int(score)))

        scored.sort(key=lambda t: t[1], reverse=True)
        return [doc for doc, _ in scored[:k]]
