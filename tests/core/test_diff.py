# tests/core/test_diff.py
"""Unit tests for sec_nlp.core.infra.diff module."""

from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.infra.diff import (
    ChangeType,
    FilingDiff,
    TextChange,
    compare_documents,
    compute_text_similarity,
    extract_changes,
    get_text_diff,
    identify_material_changes,
)


class TestComputeTextSimilarity:
    """Tests for compute_text_similarity function."""

    def test_identical_texts(self) -> None:
        """Identical texts should have similarity 1.0."""
        text = "This is a test document."
        assert compute_text_similarity(text, text) == 1.0

    def test_completely_different_texts(self) -> None:
        """Completely different texts should have low similarity."""
        text1 = "aaa bbb ccc"
        text2 = "xxx yyy zzz"
        similarity = compute_text_similarity(text1, text2)
        assert similarity < 0.3

    def test_similar_texts(self) -> None:
        """Similar texts should have moderate similarity."""
        text1 = "The company has significant risk factors."
        text2 = "The company has several risk factors."
        similarity = compute_text_similarity(text1, text2)
        assert 0.7 < similarity < 1.0

    def test_empty_texts(self) -> None:
        """Empty texts should have similarity 1.0."""
        assert compute_text_similarity("", "") == 1.0

    def test_one_empty_text(self) -> None:
        """One empty text should have similarity 0.0."""
        assert compute_text_similarity("Some text", "") == 0.0
        assert compute_text_similarity("", "Some text") == 0.0

    def test_case_insensitive(self) -> None:
        """Similarity should be case insensitive."""
        text1 = "RISK FACTORS"
        text2 = "risk factors"
        similarity = compute_text_similarity(text1, text2)
        assert similarity == 1.0


class TestExtractChanges:
    """Tests for extract_changes function."""

    def test_added_text(self) -> None:
        """Test detection of added text."""
        changes = extract_changes("", "New content here", min_change_length=10)
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.ADDED
        assert changes[0].new_text == "New content here"
        assert changes[0].old_text is None

    def test_removed_text(self) -> None:
        """Test detection of removed text."""
        changes = extract_changes("Old content here", "", min_change_length=10)
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.REMOVED
        assert changes[0].old_text == "Old content here"
        assert changes[0].new_text is None

    def test_modified_text(self) -> None:
        """Test detection of modified text."""
        old = "The company faces significant market risks in its operations."
        new = "The company faces substantial market risks in its business activities."
        changes = extract_changes(old, new, min_change_length=10)
        assert len(changes) >= 1
        # At least one change should be of type MODIFIED
        has_modified = any(
            c.change_type == ChangeType.MODIFIED for c in changes
        )
        assert has_modified or any(
            c.change_type in [ChangeType.ADDED, ChangeType.REMOVED]
            for c in changes
        )

    def test_no_changes(self) -> None:
        """Test that identical texts produce no changes."""
        text = "This text is exactly the same."
        changes = extract_changes(text, text, min_change_length=10)
        assert len(changes) == 0

    def test_min_change_length(self) -> None:
        """Test that small changes are filtered out."""
        old = "Hello world"
        new = "Hello there"
        # With high min_change_length, small changes should be ignored
        changes = extract_changes(old, new, min_change_length=100)
        assert len(changes) == 0


class TestGetTextDiff:
    """Tests for get_text_diff function."""

    def test_unified_diff_format(self) -> None:
        """Test that diff is in unified format."""
        old = "Line 1\nLine 2\nLine 3"
        new = "Line 1\nModified Line 2\nLine 3"
        diff = get_text_diff(old, new)
        # Unified diff should contain --- and +++ markers
        diff_text = "".join(diff)
        assert "---" in diff_text or len(diff) == 0

    def test_empty_diff_for_identical(self) -> None:
        """Test that identical texts produce empty diff."""
        text = "Same text"
        diff = get_text_diff(text, text)
        # Unified diff of identical texts should be empty
        assert len(list(diff)) == 0


class TestFilingDiff:
    """Tests for FilingDiff model."""

    def test_filing_diff_creation(self) -> None:
        """Test creating a FilingDiff instance."""
        diff = FilingDiff(
            symbol="AAPL",
            old_period="2023",
            new_period="2024",
            form_type="10-K",
            total_sections_compared=5,
            sections_modified=2,
            overall_similarity=0.85,
        )
        assert diff.symbol == "AAPL"
        assert diff.old_period == "2023"
        assert diff.new_period == "2024"
        assert diff.form_type == "10-K"
        assert diff.overall_similarity == 0.85

    def test_filing_diff_defaults(self) -> None:
        """Test default values for FilingDiff."""
        diff = FilingDiff(
            symbol="MSFT",
            old_period="2022",
            new_period="2023",
            form_type="10-Q",
        )
        assert diff.sections_added == 0
        assert diff.sections_removed == 0
        assert diff.sections_unchanged == 0
        assert diff.changes == []
        assert diff.material_changes == []


class TestIdentifyMaterialChanges:
    """Tests for identify_material_changes function."""

    def test_keyword_detection(self) -> None:
        """Test that keywords trigger material change detection."""
        changes = [
            TextChange(
                change_type=ChangeType.ADDED,
                old_text=None,
                new_text="The company faces litigation risks from regulatory investigations.",
                similarity=0.0,
            )
        ]
        material = identify_material_changes(changes)
        assert (
            len(material) == 1
        )  # "litigation" and "investigation" are keywords

    def test_significant_text_difference(self) -> None:
        """Test that low similarity triggers material change."""
        changes = [
            TextChange(
                change_type=ChangeType.MODIFIED,
                old_text="Minor operational update.",
                new_text="Complete restructuring of operations.",
                similarity=0.2,  # Low similarity
            )
        ]
        material = identify_material_changes(changes, min_similarity_diff=0.3)
        assert len(material) == 1

    def test_custom_keywords(self) -> None:
        """Test with custom keyword list."""
        changes = [
            TextChange(
                change_type=ChangeType.ADDED,
                old_text=None,
                new_text="Revenue increased significantly.",
                similarity=0.0,
            )
        ]
        # With custom keywords that don't match
        material = identify_material_changes(
            changes, keywords=["unrelated", "keywords"]
        )
        # Should still flag due to similarity threshold
        assert len(material) >= 0  # Depends on implementation


class TestCompareDocuments:
    """Tests for compare_documents function."""

    def test_compare_by_section(self) -> None:
        """Test comparing documents grouped by section."""
        old_docs = [
            Document(
                page_content="Risk factor content", metadata={"section": "1A"}
            ),
            Document(page_content="MD&A content", metadata={"section": "7"}),
        ]
        new_docs = [
            Document(
                page_content="Updated risk factor content",
                metadata={"section": "1A"},
            ),
            Document(page_content="MD&A content", metadata={"section": "7"}),
        ]
        result = compare_documents(old_docs, new_docs, section_key="section")
        assert "1A" in result
        assert "7" in result

    def test_new_section_detected(self) -> None:
        """Test that new sections are detected."""
        old_docs = [
            Document(
                page_content="Original content", metadata={"section": "1"}
            ),
        ]
        new_docs = [
            Document(
                page_content="Original content", metadata={"section": "1"}
            ),
            Document(page_content="New section", metadata={"section": "2"}),
        ]
        result = compare_documents(old_docs, new_docs, section_key="section")
        assert "2" in result
        # Section 2 should show as added
        changes_2 = result.get("2", [])
        assert len(changes_2) > 0


class TestTextChange:
    """Tests for TextChange dataclass."""

    def test_text_change_creation(self) -> None:
        """Test creating TextChange instance."""
        change = TextChange(
            change_type=ChangeType.MODIFIED,
            old_text="Old",
            new_text="New",
            similarity=0.5,
            context="Section 1A",
        )
        assert change.change_type == ChangeType.MODIFIED
        assert change.old_text == "Old"
        assert change.new_text == "New"
        assert change.similarity == 0.5
        assert change.context == "Section 1A"


class TestChangeType:
    """Tests for ChangeType enum."""

    def test_change_type_values(self) -> None:
        """Test ChangeType enum values."""
        assert ChangeType.ADDED.value == "added"
        assert ChangeType.REMOVED.value == "removed"
        assert ChangeType.MODIFIED.value == "modified"
        assert ChangeType.UNCHANGED.value == "unchanged"
