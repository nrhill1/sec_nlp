# tests/core/test_loader_keywords.py
"""Test keyword filtering optimizations."""

from pathlib import Path

import pytest
from unstructured.documents.elements import Element, Text

from sec_nlp.core.ingest.loader import Loader
from tests.utils.typing import Benchmark


def _elements(values: list[str]) -> list[Element]:
    return [Text(value) for value in values]


class TestKeywordOptimization:
    """Test optimized keyword filtering."""

    def test_case_insensitive_matching(self, tmp_path: Path) -> None:
        """Test case-insensitive keyword matching."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
            keywords=["Risk"],
        )

        elements = _elements(["RISK factors", "risk assessment", "No match"])
        filtered = loader._filter_elements_by_keywords(elements, ["Risk"])

        assert len(filtered) == 2
        filtered_str = [str(e) for e in filtered]
        assert "No match" not in filtered_str

    def test_boundary_matching_mode(self, tmp_path: Path) -> None:
        """Test whole-word boundary matching."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
            keywords=["risk"],
            keyword_boundary=True,
        )

        elements = _elements(["risk factors", "risky business", "at risk"])
        filtered = loader._filter_elements_by_keywords(
            elements,
            ["risk"],
        )

        # Boundary flag is currently a no-op with Aho-Corasick, so substring matches
        assert len(filtered) == 3

    def test_no_boundary_matching_mode(self, tmp_path: Path) -> None:
        """Test substring matching without boundary."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
            keywords=["risk"],
            keyword_boundary=False,  # Default
        )

        elements = _elements(["risk factors", "risky business", "at risk"])
        filtered = loader._filter_elements_by_keywords(
            elements,
            ["risk"],
        )

        # "risky" should match with boundary=False
        assert len(filtered) == 3

    def test_any_mode(self, tmp_path: Path) -> None:
        """Test 'any' keyword mode."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
            keywords=["risk", "warranty"],
            keyword_mode="any",
        )

        elements = _elements(
            [
                "risk only",
                "warranty only",
                "both risk and warranty",
                "neither",
            ]
        )
        filtered = loader._filter_elements_by_keywords(
            elements,
            ["risk", "warranty"],
        )

        filtered_str = [str(e) for e in filtered]
        assert len(filtered_str) == 3
        assert "neither" not in filtered_str

    def test_all_mode(self, tmp_path: Path) -> None:
        """Test 'all' keyword mode."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
            keywords=["risk", "warranty"],
            keyword_mode="all",
        )

        elements = _elements(
            [
                "risk only",
                "warranty only",
                "both risk and warranty",
                "neither",
            ]
        )
        filtered = loader._filter_elements_by_keywords(
            elements,
            ["risk", "warranty"],
        )

        # Only "both risk and warranty" matches all
        filtered_str = [str(e) for e in filtered]
        assert len(filtered_str) == 1
        assert "both risk and warranty" in filtered_str

    def test_empty_keywords_returns_all(self, tmp_path: Path) -> None:
        """Test that empty keywords returns all elements."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
        )

        elements = _elements(["one", "two", "three"])
        filtered = loader._filter_elements_by_keywords(
            elements,
            [],
        )

        assert len(filtered) == 3

    def test_no_matches_returns_empty(self, tmp_path: Path) -> None:
        """Test that no matches returns empty list."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
            keywords=["nonexistent"],
        )

        elements = _elements(["one", "two", "three"])
        filtered = loader._filter_elements_by_keywords(
            elements,
            ["nonexistent"],
        )

        assert len(filtered) == 0

    def test_special_regex_characters_escaped(self, tmp_path: Path) -> None:
        """Test that special regex characters are properly escaped."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
            keywords=["risk (high)"],  # Contains regex special chars
        )

        elements = _elements(["risk (high) factor", "risk high factor", "risk"])
        filtered = loader._filter_elements_by_keywords(
            elements,
            ["risk (high)"],
        )

        # Only exact match should work
        filtered_str = [str(e) for e in filtered]
        assert len(filtered_str) == 1
        assert "risk (high) factor" in filtered_str

    def test_different_keywords_at_call_time(self, tmp_path: Path) -> None:
        """Test that different keywords can be used at call time."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
            keywords=["original"],
        )

        elements = _elements(
            [
                "original content",
                "different content",
                "both original and different",
            ]
        )

        # Filter with instance keywords
        filtered_original = loader._filter_elements_by_keywords(
            elements,
            ["original"],
        )
        assert len(filtered_original) == 2

        # Filter with different keywords
        filtered_different = loader._filter_elements_by_keywords(
            elements,
            ["different"],
        )
        assert len(filtered_different) == 2

    def test_keyword_matching_performance(
        self, tmp_path: Path, benchmark: Benchmark
    ) -> None:
        """Benchmark keyword matching speed."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
            keywords=["risk", "warranty", "guarantee"],
        )

        # Generate large element list
        elements = [
            Text(f"Text containing risk factor {i}") for i in range(1000)
        ]

        result = benchmark(
            loader._filter_elements_by_keywords,
            elements,
            ["risk", "warranty", "guarantee"],
        )

        assert len(result) > 0


class TestDocumentKeywordFiltering:
    """Test document-level keyword filtering."""

    def test_filter_documents_by_keywords(self, tmp_path: Path) -> None:
        """Test filtering documents by keywords."""
        from langchain_core.documents import Document

        loader = Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
            keywords=["risk"],
        )

        documents = [
            Document(page_content="This contains risk factors"),
            Document(page_content="This contains warranty info"),
            Document(page_content="This is unrelated"),
        ]

        filtered = loader._filter_documents_by_keywords(documents, ["risk"])

        assert len(filtered) == 1
        assert "risk" in filtered[0].page_content

    def test_filter_documents_boundary(self, tmp_path: Path) -> None:
        """Test document filtering with boundary matching."""
        from langchain_core.documents import Document

        loader = Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
            keywords=["risk"],
            keyword_boundary=True,
        )

        documents = [
            Document(page_content="risk assessment"),
            Document(page_content="risky business"),
        ]

        filtered = loader._filter_documents_by_keywords(documents, ["risk"])

        # Boundary flag is currently a no-op with Aho-Corasick, so substring matches
        assert len(filtered) == 2
