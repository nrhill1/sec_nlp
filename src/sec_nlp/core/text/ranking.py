# src/sec_nlp/core/text/ranking.py
"""Unified document ranking and keyword extraction module.

Provides a high-level API for keyword extraction and document ranking
using Rust-based algorithms (YAKE, RAKE, TextRank, TF-IDF).
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from typing import TYPE_CHECKING

from langchain_core.documents import Document
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

if TYPE_CHECKING:
    from efts import (
        DocumentScore as RustDocumentScore,
        KeywordResult as RustKeywordResult,
        RakeExtractor as RustRakeExtractor,
        TextRankExtractor as RustTextRankExtractor,
        YakeExtractor as RustYakeExtractor,
    )


class RankingAlgorithm(str, Enum):
    """Available keyword extraction/ranking algorithms."""

    YAKE = "yake"
    RAKE = "rake"
    TEXTRANK = "textrank"
    TFIDF = "tfidf"
    KEYWORD_MATCH = "keyword_match"  # Simple substring matching


@dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class ExtractedKeyword:
    """Result of keyword extraction."""

    keyword: str
    score: float
    algorithm: RankingAlgorithm


@dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class RankedDocument:
    """Result of document ranking."""

    index: int
    score: float
    document: Document | None = None


@dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class TopicScore:
    """Score for a document based on topic/keyword matching."""

    total_hits: int
    keyword_counts: dict[str, int]
    normalized_score: float = 0.0


def _check_efts_available() -> bool:
    """Check if the EFTS Rust extension is available."""
    try:
        import efts  # noqa: F401

        return True
    except ImportError:
        return False


EFTS_AVAILABLE = _check_efts_available()


def _require_efts(feature: str) -> None:
    if not EFTS_AVAILABLE:
        raise RuntimeError(
            f"{feature} requires the EFTS Rust extension; Python fallback is disabled."
        )


class KeywordExtractor:
    """Unified keyword extraction using Rust backends.

    Supports YAKE, RAKE, TextRank algorithms with configurable parameters.

    Example:
        extractor = KeywordExtractor(algorithm=RankingAlgorithm.YAKE)
        keywords = extractor.extract("Some text about warranty reserves...")
        for kw in keywords:
            print(f"{kw.keyword}: {kw.score}")
    """

    def __init__(
        self,
        algorithm: RankingAlgorithm = RankingAlgorithm.YAKE,
        *,
        ngram_size: int = 3,
        threshold: float = 0.85,
        window_size: int = 2,
        damping: float = 0.85,
        tolerance: float = 0.00005,
        phrase_length: int | None = None,
    ) -> None:
        """Initialize the extractor.

        Args:
            algorithm: Which algorithm to use for extraction.
            ngram_size: Max n-gram size for YAKE (default: 3).
            threshold: Deduplication threshold for YAKE (default: 0.85).
            window_size: Context window size for YAKE/TextRank (default: 2).
            damping: Damping factor for TextRank (default: 0.85).
            tolerance: Convergence tolerance for TextRank (default: 0.00005).
            phrase_length: Max phrase length for TextRank (default: None).
        """
        self.algorithm = algorithm
        self._ngram_size = ngram_size
        self._threshold = threshold
        self._window_size = window_size
        self._damping = damping
        self._tolerance = tolerance
        self._phrase_length = phrase_length
        self._extractor: (
            RustYakeExtractor | RustRakeExtractor | RustTextRankExtractor | None
        ) = None

        _require_efts("Keyword extraction")

        self._init_extractor()

    def _init_extractor(self) -> None:
        """Initialize the appropriate Rust extractor."""
        import efts

        if self.algorithm == RankingAlgorithm.YAKE:
            self._extractor = efts.YakeExtractor(
                ngram_size=self._ngram_size,
                threshold=self._threshold,
                window_size=self._window_size,
            )
        elif self.algorithm == RankingAlgorithm.RAKE:
            self._extractor = efts.RakeExtractor()
        elif self.algorithm == RankingAlgorithm.TEXTRANK:
            self._extractor = efts.TextRankExtractor(
                window_size=self._window_size,
                damping=self._damping,
                tolerance=self._tolerance,
                phrase_length=self._phrase_length,
            )
        else:
            msg = f"Unsupported algorithm for extraction: {self.algorithm}"
            raise ValueError(msg)

    def extract(self, text: str, top_n: int = 10) -> list[ExtractedKeyword]:
        """Extract keywords from text.

        Args:
            text: Text to extract keywords from.
            top_n: Maximum number of keywords to return.

        Returns:
            List of ExtractedKeyword objects sorted by importance.
        """
        if not text or not text.strip():
            return []

        if self._extractor is None:
            return []

        results: list[RustKeywordResult] = self._extractor.extract_keywords(
            text, top_n
        )
        return [
            ExtractedKeyword(
                keyword=r.keyword,
                score=r.score,
                algorithm=self.algorithm,
            )
            for r in results
        ]


class DocumentRanker:
    """Rank documents by relevance to topics/keywords.

    Supports TF-IDF corpus-based ranking and simple keyword matching.

    Example:
        ranker = DocumentRanker()
        ranker.add_documents(["doc1 text", "doc2 text"])
        ranked = ranker.rank_by_keywords(["warranty", "liability"])
    """

    def __init__(
        self,
        algorithm: RankingAlgorithm = RankingAlgorithm.TFIDF,
    ) -> None:
        """Initialize the ranker.

        Args:
            algorithm: Ranking algorithm (TFIDF or KEYWORD_MATCH).
        """
        self.algorithm = algorithm
        self._documents: list[str] = []

        if algorithm == RankingAlgorithm.TFIDF:
            _require_efts("TF-IDF ranking")
            import efts

            self._tfidf: efts.TfIdfRanker | None = None

            self._tfidf = efts.TfIdfRanker()

    def add_documents(self, documents: Sequence[str | Document]) -> None:
        """Add documents to the corpus.

        Args:
            documents: List of document texts or Document objects.
        """
        texts = [
            d.page_content if isinstance(d, Document) else d for d in documents
        ]
        self._documents.extend(texts)

        if self._tfidf is not None:
            self._tfidf.add_documents(texts)

    def clear(self) -> None:
        """Clear all documents from the corpus."""
        self._documents.clear()
        if self._tfidf is not None:
            self._tfidf.clear()

    @property
    def document_count(self) -> int:
        """Number of documents in the corpus."""
        return len(self._documents)

    def extract_corpus_keywords(
        self, top_n: int = 10
    ) -> list[ExtractedKeyword]:
        """Extract top keywords from the entire corpus using TF-IDF.

        Args:
            top_n: Maximum number of keywords to return.

        Returns:
            List of ExtractedKeyword objects.
        """
        if self._tfidf is None or not self._documents:
            return []

        results: list[RustKeywordResult] = self._tfidf.extract_keywords(top_n)
        return [
            ExtractedKeyword(
                keyword=r.keyword,
                score=r.score,
                algorithm=RankingAlgorithm.TFIDF,
            )
            for r in results
        ]

    def rank_by_keywords(
        self,
        keywords: Sequence[str],
        *,
        top_n: int = 100,
        min_hits: int = 0,
        case_insensitive: bool = True,
    ) -> list[RankedDocument]:
        """Rank documents by keyword relevance.

        Args:
            keywords: Keywords to search for.
            top_n: Maximum number of documents to return.
            min_hits: Minimum keyword hits required.
            case_insensitive: Whether matching is case-insensitive.

        Returns:
            List of RankedDocument objects sorted by score (descending).
        """
        if not self._documents or not keywords:
            return []

        _require_efts("Keyword ranking")
        import efts

        results: list[RustDocumentScore] = efts.rank_documents_by_keywords(
            self._documents,
            list(keywords),
            case_insensitive,
            min_hits,
        )
        return [
            RankedDocument(index=r.index, score=r.score)
            for r in results[:top_n]
        ]


def score_document(
    text: str,
    keywords: Sequence[str],
    *,
    case_insensitive: bool = True,
) -> TopicScore:
    """Score a single document by keyword hits.

    Args:
        text: Document text to score.
        keywords: Keywords to search for.
        case_insensitive: Whether matching is case-insensitive.

    Returns:
        TopicScore with hit counts and normalized score.
    """
    if not text or not keywords:
        return TopicScore(total_hits=0, keyword_counts={}, normalized_score=0.0)

    _require_efts("Keyword scoring")
    import efts

    total, counts = efts.score_document_keywords(
        text, list(keywords), case_insensitive
    )
    normalized = total / len(text) * 1000 if text else 0.0
    return TopicScore(
        total_hits=total,
        keyword_counts=counts,
        normalized_score=normalized,
    )


def rank_documents(
    documents: Sequence[Document],
    keywords: Sequence[str],
    *,
    min_hits: int = 0,
    top_n: int | None = None,
    prioritize: bool = True,
) -> list[Document]:
    """Rank documents by keyword relevance using Rust backend.

    This is a convenience function for ranking langchain Document objects.

    Args:
        documents: Documents to rank.
        keywords: Keywords to search for.
        min_hits: Minimum keyword hits required to include a document.
        top_n: Maximum number of documents to return (None = all).
        prioritize: Whether to sort by score (True) or preserve order (False).

    Returns:
        List of Document objects with updated metadata (topic_score, topic_hits).
    """
    if not documents or not keywords:
        return list(documents) if documents else []

    texts = [d.page_content or "" for d in documents]

    _require_efts("Keyword ranking")
    import efts

    scores: list[RustDocumentScore] = efts.rank_documents_by_keywords(
        texts, list(keywords), True, min_hits
    )

    # Build index -> score map
    score_map: dict[int, float] = {s.index: s.score for s in scores}

    # Filter and annotate documents
    result: list[tuple[Document, float]] = []
    for idx, doc in enumerate(documents):
        score = score_map.get(idx, 0.0)
        if score >= min_hits:
            # Score the document to get detailed counts
            topic_score = score_document(doc.page_content or "", keywords)
            doc.metadata = {
                **(doc.metadata or {}),
                "topic_score": int(score),
                "topic_hits": list(topic_score.keyword_counts.keys()),
                "topic_hits_detail": topic_score.keyword_counts,
            }
            result.append((doc, score))

    if prioritize:
        result.sort(key=lambda x: x[1], reverse=True)

    ranked_docs = [d for d, _ in result]
    if top_n is not None:
        ranked_docs = ranked_docs[:top_n]

    return ranked_docs
