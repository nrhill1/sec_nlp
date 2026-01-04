# tests/core/test_filters_optimization.py
"""Tests for section filter optimization methods."""

import pytest

from sec_nlp.core.text.filters import (
    SectionFilter,
    SectionPattern,
    SectionType,
    create_exhibit_filter,
    create_item_filter,
)


@pytest.fixture
def exhibit_filter() -> SectionFilter:
    """Create an exhibit filter for testing."""
    return create_exhibit_filter(["10", "21"])


@pytest.fixture
def item_filter() -> SectionFilter:
    """Create an item filter for testing."""
    return create_item_filter(["1A", "7"])


@pytest.fixture
def multi_filter() -> SectionFilter:
    """Create a multi-section filter for testing."""
    patterns = [
        SectionPattern(section_type=SectionType.EXHIBIT, numbers=["10"]),
        SectionPattern(section_type=SectionType.ITEM, numbers=["1A"]),
    ]
    return SectionFilter(patterns=patterns)


class TestQuickCheckHtml:
    """Tests for quick_check_html method."""

    def test_detects_exhibit_keyword(
        self, exhibit_filter: SectionFilter
    ) -> None:
        """Test detection of exhibit keywords in HTML."""
        html = (
            "<html><body><h1>Exhibit 10 - Material Contract</h1></body></html>"
        )
        assert exhibit_filter.quick_check_html(html) is True

    def test_detects_exhibit_variations(
        self, exhibit_filter: SectionFilter
    ) -> None:
        """Test detection of exhibit keyword variations."""
        variations = [
            "<html><body>EXHIBIT 21</body></html>",
            "<html><body>Exh. 10.1</body></html>",
            "<html><body>EX-10</body></html>",
            "<html><body>ex-21</body></html>",
        ]
        for html in variations:
            assert exhibit_filter.quick_check_html(html) is True, (
                f"Failed for: {html}"
            )

    def test_detects_item_keyword(self, item_filter: SectionFilter) -> None:
        """Test detection of item keywords in HTML."""
        html = "<html><body><h1>Item 1A - Risk Factors</h1></body></html>"
        assert item_filter.quick_check_html(html) is True

    def test_detects_item_variations(self, item_filter: SectionFilter) -> None:
        """Test detection of item keyword variations."""
        variations = [
            "<html><body>ITEM 7</body></html>",
            "<html><body>Item No. 1A</body></html>",
        ]
        for html in variations:
            assert item_filter.quick_check_html(html) is True, (
                f"Failed for: {html}"
            )

    def test_no_match_returns_false(
        self, exhibit_filter: SectionFilter
    ) -> None:
        """Test that irrelevant content returns False."""
        html = "<html><body><p>This document contains no relevant sections.</p></body></html>"
        assert exhibit_filter.quick_check_html(html) is False

    def test_respects_check_window(self, exhibit_filter: SectionFilter) -> None:
        """Test that check_window parameter limits search area."""
        # Exhibit keyword is beyond the check window
        html = "x" * 1000 + "<h1>Exhibit 10</h1>"

        # Small window should miss it
        assert exhibit_filter.quick_check_html(html, check_window=500) is False

        # Large window should find it
        assert exhibit_filter.quick_check_html(html, check_window=2000) is True

    def test_custom_pattern_returns_true(self) -> None:
        """Test that custom patterns always return True for safety."""
        pattern = SectionPattern(
            section_type=SectionType.CUSTOM,
            custom_pattern=r"schedule\s+14a",
        )
        filter_ = SectionFilter(patterns=[pattern])

        # Custom patterns can't use quick check, so always return True
        html = "<html><body>Random content</body></html>"
        assert filter_.quick_check_html(html) is True

    def test_multi_section_filter(self, multi_filter: SectionFilter) -> None:
        """Test quick check with multiple section types."""
        # Should match exhibit
        html1 = "<html><body>Exhibit 10</body></html>"
        assert multi_filter.quick_check_html(html1) is True

        # Should match item
        html2 = "<html><body>Item 1A</body></html>"
        assert multi_filter.quick_check_html(html2) is True

        # Should not match unrelated
        html3 = "<html><body>Financial statements</body></html>"
        assert multi_filter.quick_check_html(html3) is False


class TestShouldProcessHtml:
    """Tests for should_process_html method."""

    def test_accepts_valid_content(self, exhibit_filter: SectionFilter) -> None:
        """Test that valid content passes all checks."""
        html = "<html><body><h1>Exhibit 10</h1><p>Contract details here.</p></body></html>"
        should_process, reason = exhibit_filter.should_process_html(html)
        assert should_process is True
        assert reason == "passed_all_checks"

    def test_rejects_short_content(self, exhibit_filter: SectionFilter) -> None:
        """Test that too-short content is rejected."""
        html = "<p>Short</p>"
        should_process, reason = exhibit_filter.should_process_html(html)
        assert should_process is False
        assert reason == "content_too_short"

    def test_rejects_missing_keywords(
        self, exhibit_filter: SectionFilter
    ) -> None:
        """Test rejection when no relevant section terms found."""
        html = "<html><body>" + "<p>Financial data. " * 20 + "</body></html>"
        should_process, reason = exhibit_filter.should_process_html(html)
        assert should_process is False
        assert reason == "no_relevant_section_terms"

    def test_rejects_error_pages(self, exhibit_filter: SectionFilter) -> None:
        """Test rejection of error pages."""
        html = "<html><head><title>Error</title></head><body>Exhibit 10 - Error occurred</body></html>"
        should_process, reason = exhibit_filter.should_process_html(html)
        assert should_process is False
        assert "non_content_page" in reason

    def test_rejects_404_pages(self, exhibit_filter: SectionFilter) -> None:
        """Test rejection of 404 pages."""
        html = "<html><body><h1>404 Not Found</h1><p>Exhibit 10 cannot be found.</p></body></html>"
        should_process, reason = exhibit_filter.should_process_html(html)
        assert should_process is False
        assert "non_content_page" in reason

    def test_rejects_access_denied(self, exhibit_filter: SectionFilter) -> None:
        """Test rejection of access denied pages."""
        html = "<html><body><h1>Access Denied</h1><p>Exhibit 10 requires authentication.</p></body></html>"
        should_process, reason = exhibit_filter.should_process_html(html)
        assert should_process is False
        assert "non_content_page" in reason

    def test_custom_min_content_length(
        self, exhibit_filter: SectionFilter
    ) -> None:
        """Test custom minimum content length."""
        html = "<html><body>Exhibit 10</body></html>"  # 35 chars

        # Default threshold (100) should reject
        should_process, _ = exhibit_filter.should_process_html(
            html, min_content_length=100
        )
        assert should_process is False

        # Lower threshold should accept
        should_process, _ = exhibit_filter.should_process_html(
            html, min_content_length=20
        )
        assert should_process is True


class TestBatchPrefilterHtml:
    """Tests for batch_prefilter_html method."""

    def test_filters_batch(self, exhibit_filter: SectionFilter) -> None:
        """Test batch filtering separates processable from filtered content."""
        html_list = [
            "<html><body><h1>Exhibit 10</h1><p>Valid contract content here.</p></body></html>",
            "<p>Too short</p>",
            "<html><body>" + "<p>No keywords. " * 20 + "</body></html>",
            "<html><body><h1>Exhibit 21</h1><p>List of subsidiaries.</p></body></html>",
        ]

        to_process, filtered_out = exhibit_filter.batch_prefilter_html(
            html_list
        )

        # Should process items 0 and 3
        assert len(to_process) == 2
        process_indices = [idx for idx, _ in to_process]
        assert 0 in process_indices
        assert 3 in process_indices

        # Should filter out items 1 and 2
        assert len(filtered_out) == 2
        filter_indices = [idx for idx, _, _ in filtered_out]
        assert 1 in filter_indices
        assert 2 in filter_indices

    def test_preserves_indices(self, exhibit_filter: SectionFilter) -> None:
        """Test that original indices are preserved in output."""
        html_list = [
            f"<html><body>{'Exhibit 10 content ' * 10}</body></html>",
            f"<html><body>{'No exhibit here ' * 10}</body></html>",
            f"<html><body>{'Exhibit 21 content ' * 10}</body></html>",
        ]

        to_process, filtered_out = exhibit_filter.batch_prefilter_html(
            html_list
        )

        # Check indices match original positions
        for idx, html in to_process:
            assert html == html_list[idx]

        for idx, html, _ in filtered_out:
            assert html == html_list[idx]

    def test_empty_batch(self, exhibit_filter: SectionFilter) -> None:
        """Test handling of empty batch."""
        to_process, filtered_out = exhibit_filter.batch_prefilter_html([])
        assert to_process == []
        assert filtered_out == []

    def test_all_pass(self, exhibit_filter: SectionFilter) -> None:
        """Test when all items pass filtering."""
        html_list = [
            f"<html><body><h1>Exhibit {n}</h1><p>Content here.</p></body></html>"
            for n in [10, 21, 10]
        ]

        to_process, filtered_out = exhibit_filter.batch_prefilter_html(
            html_list
        )
        assert len(to_process) == 3
        assert len(filtered_out) == 0

    def test_all_filtered(self, exhibit_filter: SectionFilter) -> None:
        """Test when all items are filtered out."""
        html_list = [
            "<p>Short</p>",
            "<html><body>No keywords here at all.</body></html>",
        ]

        to_process, filtered_out = exhibit_filter.batch_prefilter_html(
            html_list
        )
        assert len(to_process) == 0
        assert len(filtered_out) == 2

    def test_filter_reasons_provided(
        self, exhibit_filter: SectionFilter
    ) -> None:
        """Test that filter reasons are captured."""
        html_list = [
            "<p>x</p>",  # too short
            "<html><body>" + "no keywords " * 20 + "</body></html>",  # no terms
        ]

        _, filtered_out = exhibit_filter.batch_prefilter_html(html_list)

        reasons = [reason for _, _, reason in filtered_out]
        assert "content_too_short" in reasons
        assert "no_relevant_section_terms" in reasons


class TestFilterOptimizationPerformance:
    """Performance-related tests for filter optimization."""

    def test_quick_check_faster_than_full_filter(
        self, exhibit_filter: SectionFilter
    ) -> None:
        """Verify quick_check is lightweight operation."""
        import time

        # Large HTML content
        html = "<html><body>" + "<p>Some content. " * 1000 + "</body></html>"

        # Quick check should be fast
        start = time.perf_counter()
        for _ in range(100):
            exhibit_filter.quick_check_html(html)
        quick_time = time.perf_counter() - start

        # Just verify it completes quickly (under 1 second for 100 iterations)
        assert quick_time < 1.0

    def test_batch_prefilter_scales(
        self, exhibit_filter: SectionFilter
    ) -> None:
        """Test that batch prefiltering handles larger batches."""
        # Create a batch with mixed content
        html_list = []
        for i in range(100):
            if i % 3 == 0:
                html_list.append(
                    f"<html><body>Exhibit 10 - Doc {i}</body></html>"
                )
            else:
                html_list.append(
                    f"<html><body>Random content {i}</body></html>"
                )

        to_process, filtered_out = exhibit_filter.batch_prefilter_html(
            html_list
        )

        # Should have filtered appropriately
        assert len(to_process) + len(filtered_out) == 100
        # Roughly 1/3 should pass (every 3rd has "Exhibit")
        assert 30 <= len(to_process) <= 40


class TestPartFilter:
    """Tests for Part section type filtering."""

    def test_part_filter_quick_check(self) -> None:
        """Test quick check for Part sections."""
        pattern = SectionPattern(
            section_type=SectionType.PART,
            numbers=["I", "II"],
        )
        filter_ = SectionFilter(patterns=[pattern])

        html = (
            "<html><body><h1>Part I - Financial Information</h1></body></html>"
        )
        assert filter_.quick_check_html(html) is True

        html_no_part = "<html><body><h1>Section 1</h1></body></html>"
        assert filter_.quick_check_html(html_no_part) is False
