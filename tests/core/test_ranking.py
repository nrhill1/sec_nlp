# tests/core/test_ranking.py
"""Tests for the ranking module."""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

from sec_nlp.core.text.ranking import (
    EFTS_AVAILABLE,
    DocumentRanker,
    ExtractedKeyword,
    KeywordExtractor,
    RankedDocument,
    RankingAlgorithm,
    TopicScore,
    rank_documents,
    score_document,
)


class TestKeywordExtractor:
    """Tests for KeywordExtractor class."""

    @pytest.mark.skipif(
        not EFTS_AVAILABLE, reason="EFTS extension not available"
    )
    def test_yake_extraction(self) -> None:
        """Test YAKE keyword extraction."""
        extractor = KeywordExtractor(algorithm=RankingAlgorithm.YAKE)
        text = """The Company recorded warranty reserves of $10 million during the quarter.
        Warranty claims increased significantly. Product liability concerns have risen."""

        keywords = extractor.extract(text, top_n=5)

        assert len(keywords) > 0
        assert all(isinstance(kw, ExtractedKeyword) for kw in keywords)
        assert all(kw.algorithm == RankingAlgorithm.YAKE for kw in keywords)

    @pytest.mark.skipif(
        not EFTS_AVAILABLE, reason="EFTS extension not available"
    )
    def test_rake_extraction(self) -> None:
        """Test RAKE keyword extraction."""
        extractor = KeywordExtractor(algorithm=RankingAlgorithm.RAKE)
        text = """Machine learning algorithms are used for natural language processing.
        Deep learning models require large datasets for training."""

        keywords = extractor.extract(text, top_n=5)

        assert len(keywords) > 0
        assert all(isinstance(kw, ExtractedKeyword) for kw in keywords)
        assert all(kw.algorithm == RankingAlgorithm.RAKE for kw in keywords)

    @pytest.mark.skipif(
        not EFTS_AVAILABLE, reason="EFTS extension not available"
    )
    def test_textrank_extraction(self) -> None:
        """Test TextRank keyword extraction."""
        extractor = KeywordExtractor(algorithm=RankingAlgorithm.TEXTRANK)
        text = """The quick brown fox jumps over the lazy dog.
        A fast brown fox leaps across the sleepy hound."""

        keywords = extractor.extract(text, top_n=5)

        assert len(keywords) > 0
        assert all(isinstance(kw, ExtractedKeyword) for kw in keywords)
        assert all(kw.algorithm == RankingAlgorithm.TEXTRANK for kw in keywords)

    def test_empty_text_extraction(self) -> None:
        """Test extraction from empty text returns empty list."""
        extractor = KeywordExtractor(algorithm=RankingAlgorithm.YAKE)
        keywords = extractor.extract("", top_n=5)
        assert keywords == []

    def test_whitespace_text_extraction(self) -> None:
        """Test extraction from whitespace-only text returns empty list."""
        extractor = KeywordExtractor(algorithm=RankingAlgorithm.YAKE)
        keywords = extractor.extract("   \n\t  ", top_n=5)
        assert keywords == []


class TestDocumentRanker:
    """Tests for DocumentRanker class."""

    @pytest.mark.skipif(
        not EFTS_AVAILABLE, reason="EFTS extension not available"
    )
    def test_tfidf_ranker(self) -> None:
        """Test TF-IDF document ranking."""
        ranker = DocumentRanker(algorithm=RankingAlgorithm.TFIDF)
        ranker.add_documents(
            [
                "Warranty reserves increased to $10 million.",
                "Product liability remains a concern.",
                "Revenue growth was strong this quarter.",
            ]
        )

        assert ranker.document_count == 3

        keywords = ranker.extract_corpus_keywords(top_n=5)
        assert len(keywords) > 0

    @pytest.mark.skipif(
        not EFTS_AVAILABLE, reason="EFTS extension not available"
    )
    def test_rank_by_keywords(self) -> None:
        """Test document ranking by keywords."""
        ranker = DocumentRanker()
        ranker.add_documents(
            [
                "This document mentions warranty once.",
                "Warranty warranty warranty - lots of warranty claims.",
                "No relevant keywords here.",
            ]
        )

        ranked = ranker.rank_by_keywords(["warranty"], min_hits=1)

        assert len(ranked) == 2
        assert all(isinstance(r, RankedDocument) for r in ranked)
        # Document with most hits should be first
        assert ranked[0].score > ranked[1].score

    def test_empty_documents_ranking(self) -> None:
        """Test ranking with no documents returns empty list."""
        ranker = DocumentRanker()
        ranked = ranker.rank_by_keywords(["warranty"])
        assert ranked == []

    def test_clear_documents(self) -> None:
        """Test clearing documents."""
        ranker = DocumentRanker()
        ranker.add_documents(["doc1", "doc2"])
        assert ranker.document_count == 2
        ranker.clear()
        assert ranker.document_count == 0


class TestScoreDocument:
    """Tests for score_document function."""

    @pytest.mark.skipif(
        not EFTS_AVAILABLE, reason="EFTS extension not available"
    )
    def test_score_document_basic(self) -> None:
        """Test basic document scoring."""
        text = (
            "The Company recorded warranty reserves. Warranty claims increased."
        )
        result = score_document(text, ["warranty", "reserves"])

        assert isinstance(result, TopicScore)
        assert result.total_hits == 3
        assert result.keyword_counts["warranty"] == 2
        assert result.keyword_counts["reserves"] == 1

    def test_score_document_empty(self) -> None:
        """Test scoring empty text."""
        result = score_document("", ["warranty"])
        assert result.total_hits == 0
        assert result.keyword_counts == {}

    def test_score_document_no_keywords(self) -> None:
        """Test scoring with no keywords."""
        result = score_document("Some text here", [])
        assert result.total_hits == 0
        assert result.keyword_counts == {}

    @pytest.mark.skipif(
        not EFTS_AVAILABLE, reason="EFTS extension not available"
    )
    def test_score_document_case_insensitive(self) -> None:
        """Test case-insensitive scoring."""
        text = "WARRANTY claims and warranty RESERVES"
        result = score_document(
            text, ["warranty", "reserves"], case_insensitive=True
        )

        assert result.total_hits == 3
        assert result.keyword_counts["warranty"] == 2
        assert result.keyword_counts["reserves"] == 1


class TestRankDocuments:
    """Tests for rank_documents function."""

    @pytest.mark.skipif(
        not EFTS_AVAILABLE, reason="EFTS extension not available"
    )
    def test_rank_documents_basic(self) -> None:
        """Test basic document ranking."""
        docs = [
            Document(page_content="Document one mentions warranty."),
            Document(page_content="Warranty warranty warranty claims."),
            Document(page_content="No keywords here."),
        ]

        ranked = rank_documents(docs, ["warranty"], min_hits=1)

        assert len(ranked) == 2
        # Document with most hits should be first
        assert (
            ranked[0].metadata["topic_score"]
            >= ranked[1].metadata["topic_score"]
        )
        assert "topic_hits" in ranked[0].metadata
        assert "warranty" in ranked[0].metadata["topic_hits"]

    def test_rank_documents_empty(self) -> None:
        """Test ranking empty document list."""
        result = rank_documents([], ["warranty"])
        assert result == []

    def test_rank_documents_no_keywords(self) -> None:
        """Test ranking with no keywords."""
        docs = [Document(page_content="Some text")]
        result = rank_documents(docs, [])
        assert result == docs

    @pytest.mark.skipif(
        not EFTS_AVAILABLE, reason="EFTS extension not available"
    )
    def test_rank_documents_top_n(self) -> None:
        """Test top_n limiting."""
        docs = [Document(page_content=f"warranty {i}") for i in range(10)]

        ranked = rank_documents(docs, ["warranty"], top_n=3)
        assert len(ranked) == 3

    @pytest.mark.skipif(
        not EFTS_AVAILABLE, reason="EFTS extension not available"
    )
    def test_rank_documents_min_hits(self) -> None:
        """Test min_hits filtering."""
        docs = [
            Document(page_content="warranty"),
            Document(page_content="warranty warranty warranty"),
            Document(page_content="no match"),
        ]

        ranked = rank_documents(docs, ["warranty"], min_hits=2)
        assert len(ranked) == 1
        assert ranked[0].metadata["topic_score"] >= 2
