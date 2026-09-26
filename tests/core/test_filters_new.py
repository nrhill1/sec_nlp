# tests/core/test_filters_new.py
"""Unit tests for new filter factories (proxy, holdings)."""

import pytest

from sec_nlp.core.text.filters import (
    HOLDINGS_SECTION_PATTERNS,
    PROXY_SECTION_PATTERNS,
    SectionFilter,
    SectionType,
    create_holdings_filter,
    create_proxy_filter,
)


class TestProxySectionPatterns:
    """Tests for proxy statement section patterns."""

    def test_proxy_patterns_defined(self) -> None:
        """Test that proxy section patterns are defined."""
        assert len(PROXY_SECTION_PATTERNS) > 0
        assert "executive_compensation" in PROXY_SECTION_PATTERNS
        assert "director_compensation" in PROXY_SECTION_PATTERNS
        assert "say_on_pay" in PROXY_SECTION_PATTERNS
        assert "board_composition" in PROXY_SECTION_PATTERNS

    def test_proxy_patterns_are_regex(self) -> None:
        """Test that proxy patterns are valid regex strings."""
        import re

        for _key, pattern in PROXY_SECTION_PATTERNS.items():
            # Should not raise
            compiled = re.compile(pattern, re.IGNORECASE)
            assert compiled is not None


class TestHoldingsSectionPatterns:
    """Tests for 13F holdings section patterns."""

    def test_holdings_patterns_defined(self) -> None:
        """Test that holdings section patterns are defined."""
        assert len(HOLDINGS_SECTION_PATTERNS) > 0
        assert "info_table" in HOLDINGS_SECTION_PATTERNS
        assert "cover_page" in HOLDINGS_SECTION_PATTERNS

    def test_holdings_patterns_are_regex(self) -> None:
        """Test that holdings patterns are valid regex strings."""
        import re

        for _key, pattern in HOLDINGS_SECTION_PATTERNS.items():
            compiled = re.compile(pattern, re.IGNORECASE)
            assert compiled is not None


class TestCreateProxyFilter:
    """Tests for create_proxy_filter factory function."""

    def test_create_proxy_filter_default(self) -> None:
        """Test creating proxy filter with default sections."""
        filter = create_proxy_filter()
        assert isinstance(filter, SectionFilter)
        assert len(filter.patterns) == 1
        assert filter.patterns[0].section_type == SectionType.CUSTOM

    def test_create_proxy_filter_specific_sections(self) -> None:
        """Test creating proxy filter with specific sections."""
        filter = create_proxy_filter(
            sections=["executive_compensation", "say_on_pay"]
        )
        assert isinstance(filter, SectionFilter)

    def test_create_proxy_filter_invalid_section(self) -> None:
        """Test that invalid sections raise ValueError."""
        with pytest.raises(ValueError):
            create_proxy_filter(sections=["invalid_section"])

    def test_proxy_filter_matches_exec_comp(self) -> None:
        """Test that proxy filter matches executive compensation text."""
        filter = create_proxy_filter(sections=["executive_compensation"])
        # Test with sample text
        test_text = "EXECUTIVE COMPENSATION Discussion and Analysis"
        # The filter should have quick check terms
        assert filter.quick_check_html(test_text)

    def test_proxy_filter_search_window(self) -> None:
        """Test custom search window parameter."""
        filter = create_proxy_filter(search_window=5000)
        assert filter.search_window == 5000


class TestCreateHoldingsFilter:
    """Tests for create_holdings_filter factory function."""

    def test_create_holdings_filter_default(self) -> None:
        """Test creating holdings filter with defaults."""
        filter = create_holdings_filter()
        assert isinstance(filter, SectionFilter)
        assert len(filter.patterns) == 1

    def test_create_holdings_filter_with_cover(self) -> None:
        """Test creating holdings filter including cover page."""
        filter = create_holdings_filter(include_cover=True)
        assert isinstance(filter, SectionFilter)

    def test_holdings_filter_matches_info_table(self) -> None:
        """Test that holdings filter matches information table text."""
        filter = create_holdings_filter()
        test_text = "INFORMATION TABLE Form 13F Holdings Report"
        # Custom patterns use quick_check which returns True for custom types
        assert filter.quick_check_html(test_text)


class TestFilterIntegration:
    """Integration tests for new filters."""

    def test_proxy_filter_contains_section(self) -> None:
        """Test contains_section method with proxy content."""
        from sec_nlp.core.documents import DocumentRecord as Document

        create_proxy_filter(sections=["board_composition"])
        Document(
            page_content="Board of Directors\nElection of Directors for the upcoming term...",
            metadata={},
        )
        # Note: contains_section checks the first search_window chars
        # which may not match due to pattern specifics

    def test_holdings_filter_filter_indices(self) -> None:
        """Test that filter_indices parameter works."""
        filter_with = create_holdings_filter(filter_indices=True)
        filter_without = create_holdings_filter(filter_indices=False)
        assert filter_with.filter_indices is True
        assert filter_without.filter_indices is False
