# src/sec_nlp/core/diff.py
"""Diff utilities for comparing SEC filings across periods or companies."""

import difflib
from enum import StrEnum

from langchain_core.documents import Document
from pydantic import BaseModel, ConfigDict, Field
from pydantic.dataclasses import dataclass

from sec_nlp.types import JsonObject


class ChangeType(StrEnum):
    """Types of changes detected between filings."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


@dataclass
class TextChange:
    """Represents a change between two text sections."""

    change_type: ChangeType
    old_text: str | None
    new_text: str | None
    similarity: float  # 0.0 = completely different, 1.0 = identical
    context: str | None = None  # Section or heading context


class FilingDiff(BaseModel):
    """Result of comparing two filings."""

    model_config = ConfigDict(
        frozen=True,
        extra="allow",
    )

    symbol: str
    old_period: str
    new_period: str
    old_filing_date: str | None = None
    new_filing_date: str | None = None
    form_type: str

    # Summary metrics
    total_sections_compared: int = 0
    sections_added: int = 0
    sections_removed: int = 0
    sections_modified: int = 0
    sections_unchanged: int = 0

    # Overall similarity
    overall_similarity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall text similarity between filings (0-1)",
    )

    # Detailed changes by section
    changes: list[JsonObject] = Field(default_factory=list)

    # Material changes detected (high-priority changes)
    material_changes: list[JsonObject] = Field(default_factory=list)


class CompanyComparison(BaseModel):
    """Result of comparing filings across companies."""

    model_config = {"frozen": True, "extra": "allow"}

    symbols: list[str]
    period: str
    form_type: str

    # Per-company summaries
    company_summaries: dict[str, JsonObject] = Field(default_factory=dict)

    # Cross-company comparisons
    comparisons: list[JsonObject] = Field(default_factory=list)

    # Common themes across companies
    common_themes: list[str] = Field(default_factory=list)

    # Unique items per company
    unique_items: dict[str, list[str]] = Field(default_factory=dict)


def compute_text_similarity(text1: str, text2: str) -> float:
    """Compute similarity ratio between two texts using difflib.

    Args:
        text1: First text to compare
        text2: Second text to compare

    Returns:
        Similarity ratio between 0.0 and 1.0
    """
    if not text1 and not text2:
        return 1.0
    if not text1 or not text2:
        return 0.0

    # Normalize texts
    text1_norm = text1.lower().strip()
    text2_norm = text2.lower().strip()

    matcher = difflib.SequenceMatcher(None, text1_norm, text2_norm)
    return matcher.ratio()


def get_text_diff(
    old_text: str,
    new_text: str,
    context_lines: int = 3,
) -> list[str]:
    """Generate unified diff between two texts.

    Args:
        old_text: Original text
        new_text: New text
        context_lines: Number of context lines to include

    Returns:
        List of diff lines
    """
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile="old",
        tofile="new",
        n=context_lines,
    )
    return list(diff)


def extract_changes(
    old_text: str,
    new_text: str,
    min_change_length: int = 50,
) -> list[TextChange]:
    """Extract specific changes between two texts.

    Args:
        old_text: Original text
        new_text: New text
        min_change_length: Minimum length of text to consider as a change

    Returns:
        List of TextChange objects describing the differences
    """
    changes: list[TextChange] = []

    if not old_text and new_text:
        changes.append(
            TextChange(
                change_type=ChangeType.ADDED,
                old_text=None,
                new_text=new_text,
                similarity=0.0,
            )
        )
        return changes

    if old_text and not new_text:
        changes.append(
            TextChange(
                change_type=ChangeType.REMOVED,
                old_text=old_text,
                new_text=None,
                similarity=0.0,
            )
        )
        return changes

    # Use SequenceMatcher to find matching and non-matching blocks
    matcher = difflib.SequenceMatcher(None, old_text, new_text)
    opcodes = matcher.get_opcodes()

    # Aggregate adjacent small edits into a single change region
    pending_old: list[str] = []
    pending_new: list[str] = []

    def flush_pending() -> None:
        nonlocal pending_old, pending_new
        if not pending_old and not pending_new:
            return
        old_chunk = "".join(pending_old)
        new_chunk = "".join(pending_new)
        # Enforce minimum size threshold
        if (
            len(old_chunk) < min_change_length
            and len(new_chunk) < min_change_length
        ):
            pending_old = []
            pending_new = []
            return
        if old_chunk and new_chunk:
            changes.append(
                TextChange(
                    change_type=ChangeType.MODIFIED,
                    old_text=old_chunk,
                    new_text=new_chunk,
                    similarity=compute_text_similarity(old_chunk, new_chunk),
                )
            )
        elif old_chunk:
            changes.append(
                TextChange(
                    change_type=ChangeType.REMOVED,
                    old_text=old_chunk,
                    new_text=None,
                    similarity=0.0,
                )
            )
        elif new_chunk:
            changes.append(
                TextChange(
                    change_type=ChangeType.ADDED,
                    old_text=None,
                    new_text=new_chunk,
                    similarity=0.0,
                )
            )
        pending_old = []
        pending_new = []

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            # Boundary between change regions
            flush_pending()
            continue
        old_slice = old_text[i1:i2]
        new_slice = new_text[j1:j2]
        # Accumulate diffs (replace/insert/delete) into the current region
        if old_slice:
            pending_old.append(old_slice)
        if new_slice:
            pending_new.append(new_slice)

    # Flush any trailing changes
    flush_pending()

    # Fallback: if texts differ but aggregation produced no changes, emit a single MODIFIED
    if not changes and old_text != new_text:
        if (
            len(old_text) >= min_change_length
            or len(new_text) >= min_change_length
        ):
            changes.append(
                TextChange(
                    change_type=ChangeType.MODIFIED,
                    old_text=old_text,
                    new_text=new_text,
                    similarity=compute_text_similarity(old_text, new_text),
                )
            )

    return changes


def compare_documents(
    old_docs: list[Document],
    new_docs: list[Document],
    section_key: str = "section",
) -> dict[str, list[TextChange]]:
    """Compare documents grouped by section.

    Args:
        old_docs: Documents from the older filing
        new_docs: Documents from the newer filing
        section_key: Metadata key to use for section grouping

    Returns:
        Dict mapping section names to their changes
    """
    # Group documents by section
    old_by_section: dict[str, str] = {}
    new_by_section: dict[str, str] = {}

    for doc in old_docs:
        section = doc.metadata.get(section_key, "unknown")
        if section in old_by_section:
            old_by_section[section] += "\n\n" + doc.page_content
        else:
            old_by_section[section] = doc.page_content

    for doc in new_docs:
        section = doc.metadata.get(section_key, "unknown")
        if section in new_by_section:
            new_by_section[section] += "\n\n" + doc.page_content
        else:
            new_by_section[section] = doc.page_content

    # Compare each section
    all_sections = set(old_by_section.keys()) | set(new_by_section.keys())
    results: dict[str, list[TextChange]] = {}

    for section in all_sections:
        old_text = old_by_section.get(section, "")
        new_text = new_by_section.get(section, "")
        changes = extract_changes(old_text, new_text)

        # Add section context to each change
        for change in changes:
            change.context = section

        results[section] = changes

    return results


def identify_material_changes(
    changes: list[TextChange],
    keywords: list[str] | None = None,
    min_similarity_diff: float = 0.3,
) -> list[TextChange]:
    """Identify potentially material changes from a list of changes.

    Args:
        changes: List of TextChange objects
        keywords: Keywords that indicate material changes
        min_similarity_diff: Minimum difference in similarity to flag (1 - similarity)

    Returns:
        List of changes flagged as potentially material
    """
    if keywords is None:
        keywords = [
            "material",
            "significant",
            "substantial",
            "risk",
            "litigation",
            "lawsuit",
            "investigation",
            "default",
            "breach",
            "impairment",
            "writedown",
            "restructuring",
            "layoff",
            "executive",
            "ceo",
            "cfo",
            "board",
            "acquisition",
            "merger",
            "divestiture",
            "debt",
            "covenant",
            "going concern",
        ]

    keywords_lower = [k.lower() for k in keywords]
    material_changes: list[TextChange] = []

    for change in changes:
        is_material = False

        # Check if change involves significant text difference
        if change.similarity < (1 - min_similarity_diff):
            is_material = True

        # Check for keywords in added or modified text
        text_to_check = ""
        if change.new_text:
            text_to_check += change.new_text.lower()
        if change.old_text:
            text_to_check += change.old_text.lower()

        for keyword in keywords_lower:
            if keyword in text_to_check:
                is_material = True
                break

        if is_material:
            material_changes.append(change)

    return material_changes
