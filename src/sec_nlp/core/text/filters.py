# src/sec_nlp/core/text/filters.py
# src/sec_nlp/core/filters.py
"""Generalized filtering for sections, items, and exhibits in SEC documents."""

import re
from enum import StrEnum

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.text.section_patterns import (
    HOLDINGS_SECTION_PATTERNS,
    PROXY_SECTION_PATTERNS,
)


class SectionType(StrEnum):
    """Types of sections in SEC filings."""

    ITEM = "item"  # Items (e.g., Item 1A, Item 7)
    EXHIBIT = "exhibit"  # Exhibits (e.g., Exhibit 10, Exhibit 21)
    PART = "part"  # Parts (e.g., Part I, Part II)
    CUSTOM = "custom"  # Custom pattern


class SectionPattern(BaseModel):
    """Pattern configuration for matching SEC document sections."""

    section_type: SectionType = Field(
        description="Type of section to match",
    )
    numbers: list[str] = Field(
        default_factory=list,
        description="Section numbers to match (e.g., ['10', '21'] for exhibits)",
    )
    custom_pattern: str | None = Field(
        default=None,
        description="Custom regex pattern (only used when section_type=CUSTOM)",
    )
    require_exact_match: bool = Field(
        default=False,
        description="Whether to require exact number match (10 vs 10.1)",
    )

    @field_validator("custom_pattern")
    @classmethod
    def validate_custom_pattern(
        cls, v: str | None, info: ValidationInfo
    ) -> str | None:
        if info.data.get("section_type") == SectionType.CUSTOM and not v:
            raise ValueError(
                "custom_pattern is required when section_type=CUSTOM"
            )
        return v


class SectionFilter:
    """Generalized filter for SEC document sections.

    Includes optimization methods for pre-filtering HTML content before
    full parsing to improve performance on large document batches.
    """

    # Quick check patterns for lightweight pre-filtering (substring matching)
    # These are simpler patterns used for fast initial screening
    QUICK_CHECK_TERMS: dict[SectionType, list[str]] = {
        SectionType.ITEM: ["item", "Item", "ITEM"],
        SectionType.EXHIBIT: [
            "exhibit",
            "Exhibit",
            "EXHIBIT",
            "exh",
            "Exh",
            "EXH",
            "ex-",
            "EX-",
        ],
        SectionType.PART: ["part", "Part", "PART"],
    }

    WILDCARD_NUMBERS: set[str] = {"*", "any", "all"}

    ANY_NUMBER_PATTERNS: dict[SectionType, str] = {
        SectionType.ITEM: r"\d+(?:\.\d+)?[a-z]?",
        SectionType.EXHIBIT: r"\d+(?:\.\d+)?",
        SectionType.PART: r"[ivxIVX]+",
    }

    # Base patterns for different section types
    BASE_PATTERNS: dict[SectionType, list[str]] = {
        SectionType.ITEM: [
            r"item\s+{number}(?:\s|\.|\)|$)",  # "Item 1A", "Item 7.", "Item 1)"
            r"item\s+no\.\s*{number}",  # "Item No. 1A"
            r"^{number}\.\s+",  # "1. " at start of line (numbered list)
        ],
        SectionType.EXHIBIT: [
            r"exhibit\s+{number}(?:\.\d+)?",  # "Exhibit 10" or "Exhibit 10.1"
            r"exhibit\s+{number}\s*-\s*\d+",  # "Exhibit 10-1"
            r"exh\.?\s+{number}(?:\.\d+)?",  # "Exh 10" or "Exh. 10.1"
            r"ex-?{number}(?:\.\d+)?",  # "EX-10" or "EX10.1"
        ],
        SectionType.PART: [
            r"part\s+{number}",  # "Part I", "Part II"
            r"part\s+{number}\s*-",  # "Part I -"
        ],
    }

    # Additional patterns for numbered sub-sections
    SUBSECTION_PATTERNS: dict[SectionType, str] = {
        SectionType.EXHIBIT: r"exhibit\s+{number}\.(\d+)",
        SectionType.ITEM: r"item\s+{number}[a-z]",
    }

    def __init__(
        self,
        patterns: list[SectionPattern],
        search_window: int = 2000,
        filter_indices: bool = True,
    ):
        """Initialize section filter.

        Args:
            patterns: List of section patterns to match
            search_window: Number of characters to search at document start
            filter_indices: Whether to filter out index/TOC documents
        """
        self.patterns = patterns
        self.search_window = search_window
        self.filter_indices = filter_indices

        # Compile regex patterns for efficiency
        self._compiled_patterns = self._compile_patterns()

    def _compile_patterns(
        self,
    ) -> list[tuple[SectionPattern, list[re.Pattern[str]]]]:
        """Compile regex patterns for all configured section patterns."""
        compiled = []

        for pattern_config in self.patterns:
            if pattern_config.section_type == SectionType.CUSTOM:
                # Use custom pattern directly
                if pattern_config.custom_pattern:
                    compiled.append(
                        (
                            pattern_config,
                            [
                                re.compile(
                                    pattern_config.custom_pattern, re.IGNORECASE
                                )
                            ],
                        )
                    )
            else:
                # Generate patterns from base templates
                base_patterns = self.BASE_PATTERNS.get(
                    pattern_config.section_type, []
                )
                section_patterns = []

                numbers = (
                    pattern_config.numbers if pattern_config.numbers else ["*"]
                )
                for number in numbers:
                    number_value = str(number)
                    is_wildcard = number_value.lower() in self.WILDCARD_NUMBERS
                    number_pattern = (
                        self.ANY_NUMBER_PATTERNS.get(
                            pattern_config.section_type, r"\w+"
                        )
                        if is_wildcard
                        else re.escape(number_value)
                    )
                    for base_pattern in base_patterns:
                        # Replace {number} placeholder with actual number
                        pattern_str = base_pattern.replace(
                            "{number}", number_pattern
                        )

                        # If not requiring exact match, allow sub-sections
                        if (
                            not is_wildcard
                            and not pattern_config.require_exact_match
                        ):
                            # Allow optional sub-section numbers
                            if (
                                pattern_config.section_type
                                == SectionType.EXHIBIT
                            ):
                                pattern_str = pattern_str.replace(
                                    re.escape(number_value),
                                    re.escape(number_value) + r"(?:\.\d+)?",
                                )
                            elif (
                                pattern_config.section_type == SectionType.ITEM
                            ):
                                pattern_str = pattern_str.replace(
                                    re.escape(number_value),
                                    re.escape(number_value) + r"[a-z]?",
                                )

                        section_patterns.append(
                            re.compile(
                                pattern_str, re.IGNORECASE | re.MULTILINE
                            )
                        )

                compiled.append((pattern_config, section_patterns))

        return compiled

    def filter_documents(self, docs: list[Document]) -> list[Document]:
        """Filter documents for sections matching configured patterns.

        Args:
            docs: List of documents to filter

        Returns:
            Filtered list of documents containing matching sections
        """
        # First pass: filter by section patterns
        matching_docs = [doc for doc in docs if self.contains_section(doc)]

        # Second pass: filter out indices if configured
        if self.filter_indices:
            matching_docs = self._filter_non_content(matching_docs)

        logger.debug(
            "Filtered %d/%d documents matching section patterns",
            len(matching_docs),
            len(docs),
        )

        return matching_docs

    def contains_section(self, doc: Document) -> bool:
        """Check if document contains any matching section.

        Args:
            doc: Document to check

        Returns:
            True if document matches any configured pattern
        """
        # Get searchable content (beginning of document)
        content = doc.page_content[: self.search_window]

        # Check all compiled patterns
        for _pattern_config, compiled_patterns in self._compiled_patterns:
            for pattern in compiled_patterns:
                if pattern.search(content):
                    return True

        return False

    def extract_section_info(
        self, doc: Document
    ) -> dict[str, list[dict[str, str]] | bool]:
        """Extract section information from document.

        Args:
            doc: Document to extract from

        Returns:
            Dictionary with section type, number, and sub-section info
        """
        content = doc.page_content[: self.search_window]
        section_info: dict[str, list[dict[str, str]] | bool] = {
            "sections": [],
            "has_subsections": False,
        }

        for pattern_config, compiled_patterns in self._compiled_patterns:
            for pattern in compiled_patterns:
                match = pattern.search(content)
                if match:
                    section_data: dict[str, str] = {
                        "section_type": pattern_config.section_type.value,
                        "pattern": pattern.pattern,
                        "match": match.group(0),
                    }

                    # Extract number if in capture group
                    if match.groups():
                        section_data["number"] = match.group(1)
                        section_info["has_subsections"] = True

                    sections_list = section_info["sections"]
                    if isinstance(sections_list, list):
                        sections_list.append(section_data)

        return section_info

    def is_index_document(self, doc: Document) -> bool:
        """Check if document is an index/table of contents.

        Indices typically have many section references but no actual content.

        Args:
            doc: Document to check

        Returns:
            True if document appears to be an index
        """
        content = doc.page_content.lower()

        # Look for index indicators
        index_indicators = [
            "table of contents",
            "index to",
            "list of exhibits",
            "exhibits filed",
            "exhibit index",
            "documents incorporated by reference",
        ]

        has_index_indicator = any(
            indicator in content for indicator in index_indicators
        )

        # Count section references (high density suggests index)
        section_count = 0
        for _pattern_config, compiled_patterns in self._compiled_patterns:
            for pattern in compiled_patterns:
                section_count += len(
                    pattern.findall(content[: self.search_window * 2])
                )

        # If it has an index indicator OR many section references, likely an index
        return has_index_indicator or section_count > 5

    def _filter_non_content(self, docs: list[Document]) -> list[Document]:
        """Remove index documents and other non-content documents.

        Args:
            docs: List of documents to filter

        Returns:
            Filtered list with only content documents
        """
        content_docs = [doc for doc in docs if not self.is_index_document(doc)]

        if len(content_docs) < len(docs):
            logger.debug(
                "Filtered out %d index/non-content documents",
                len(docs) - len(content_docs),
            )

        return content_docs

    # ==================== Optimization Methods ====================

    def quick_check_html(
        self, html: str, check_window: int | None = None
    ) -> bool:
        """Perform a fast preliminary check on raw HTML content.

        This method uses simple substring matching to quickly determine if
        HTML content is likely to contain relevant sections. It's designed
        to be very fast (O(n) single pass) and filter out obviously
        irrelevant content before expensive parsing.

        Args:
            html: Raw HTML content to check
            check_window: Optional window size for the check. If None,
                uses self.search_window. Use a smaller window for faster
                checks on large documents.

        Returns:
            True if HTML might contain relevant sections (requires full parsing),
            False if HTML definitely does not contain relevant sections
        """
        window = (
            check_window if check_window is not None else self.search_window
        )
        # Check both start and a portion from the middle for better coverage
        snippets = [html[:window]]
        if len(html) > window * 2:
            mid_start = max(len(html) // 2 - window // 2, 0)
            snippets.append(html[mid_start : mid_start + window])

        check_content = "\n".join(snippets)

        # Collect all relevant quick-check terms based on configured patterns
        terms_to_check: set[str] = set()
        for pattern_config in self.patterns:
            if pattern_config.section_type == SectionType.CUSTOM:
                # For custom patterns, fall back to full check
                # (can't reliably do substring matching)
                return True
            section_terms = self.QUICK_CHECK_TERMS.get(
                pattern_config.section_type, []
            )
            terms_to_check.update(section_terms)

        # Fast substring check - any match means "maybe relevant"
        return any(term in check_content for term in terms_to_check)

    def should_process_html(
        self,
        html: str,
        check_window: int | None = None,
        min_content_length: int = 40,
    ) -> tuple[bool, str]:
        """Determine if HTML should be fully processed based on pre-filtering.

        This method combines multiple fast checks to decide if content should
        be processed. Use this as a gate before expensive parsing operations.

        Args:
            html: Raw HTML content to evaluate
            check_window: Optional window size for quick_check_html
            min_content_length: Minimum content length to process. Content
                shorter than this is likely incomplete or boilerplate.

        Returns:
            Tuple of (should_process: bool, reason: str)
            - should_process: True if content should be fully parsed
            - reason: Description of why content was filtered or accepted
        """
        # Check 1: Minimum length
        if len(html) < min_content_length:
            return False, "content_too_short"

        # Check 2: Quick substring check for relevant terms
        if not self.quick_check_html(html, check_window):
            return False, "no_relevant_section_terms"

        # Check 3: Filter obvious non-content pages
        html_lower = html[:2000].lower()
        non_content_indicators = [
            "<title>error</title>",
            "page not found",
            "404 not found",
            "access denied",
            "<title>loading</title>",
        ]
        for indicator in non_content_indicators:
            if indicator in html_lower:
                return False, f"non_content_page:{indicator}"

        return True, "passed_all_checks"

    def batch_prefilter_html(
        self,
        html_list: list[str],
        check_window: int | None = None,
        min_content_length: int = 40,
    ) -> tuple[list[tuple[int, str]], list[tuple[int, str, str]]]:
        """Pre-filter a batch of HTML content for processing.

        Efficiently filters a batch of HTML strings, separating those that
        should be processed from those that can be skipped.

        Args:
            html_list: List of raw HTML strings to filter
            check_window: Optional window size for quick checks
            min_content_length: Minimum content length threshold

        Returns:
            Tuple of:
            - to_process: List of (index, html) tuples that passed filtering
            - filtered_out: List of (index, html, reason) tuples that were filtered
        """
        to_process: list[tuple[int, str]] = []
        filtered_out: list[tuple[int, str, str]] = []

        for idx, html in enumerate(html_list):
            should_process, reason = self.should_process_html(
                html, check_window, min_content_length
            )
            if should_process:
                to_process.append((idx, html))
            else:
                filtered_out.append((idx, html, reason))

        if filtered_out:
            logger.debug(
                "Pre-filtered %d/%d HTML documents before parsing",
                len(filtered_out),
                len(html_list),
            )

        return to_process, filtered_out


# Convenience factory functions
def create_default_section_filter(
    search_window: int = 2000,
    filter_indices: bool = True,
) -> SectionFilter:
    """Create a default filter that matches common section headers.

    This enables section-aware chunking without requiring explicit numbers.
    """
    patterns = [
        SectionPattern(section_type=SectionType.ITEM, numbers=["*"]),
        SectionPattern(section_type=SectionType.PART, numbers=["*"]),
        SectionPattern(section_type=SectionType.EXHIBIT, numbers=["*"]),
    ]
    return SectionFilter(
        patterns=patterns,
        search_window=search_window,
        filter_indices=filter_indices,
    )


def create_exhibit_filter(
    exhibit_numbers: list[str],
    search_window: int = 2000,
    filter_indices: bool = True,
) -> SectionFilter:
    """Create a filter for specific exhibits.

    Args:
        exhibit_numbers: List of exhibit numbers (e.g., ["10", "21"])
        search_window: Search window size
        filter_indices: Whether to filter indices

    Returns:
        Configured SectionFilter for exhibits
    """
    pattern = SectionPattern(
        section_type=SectionType.EXHIBIT,
        numbers=exhibit_numbers,
        require_exact_match=False,
    )
    return SectionFilter(
        patterns=[pattern],
        search_window=search_window,
        filter_indices=filter_indices,
    )


def create_item_filter(
    item_numbers: list[str],
    search_window: int = 2000,
    filter_indices: bool = True,
) -> SectionFilter:
    """Create a filter for specific items.

    Args:
        item_numbers: List of item numbers (e.g., ["1A", "7", "1.01"])
        search_window: Search window size
        filter_indices: Whether to filter indices

    Returns:
        Configured SectionFilter for items
    """
    pattern = SectionPattern(
        section_type=SectionType.ITEM,
        numbers=item_numbers,
        require_exact_match=False,
    )
    return SectionFilter(
        patterns=[pattern],
        search_window=search_window,
        filter_indices=filter_indices,
    )


def create_multi_section_filter(
    patterns: list[SectionPattern],
    search_window: int = 2000,
    filter_indices: bool = True,
) -> SectionFilter:
    """Create a filter for multiple section types.

    Args:
        patterns: List of section patterns to match
        search_window: Search window size
        filter_indices: Whether to filter indices

    Returns:
        Configured SectionFilter for multiple sections
    """
    return SectionFilter(
        patterns=patterns,
        search_window=search_window,
        filter_indices=filter_indices,
    )


# ==================== DEF 14A (Proxy) Filters ====================
def create_proxy_filter(
    sections: list[str] | None = None,
    search_window: int = 3000,
    filter_indices: bool = True,
) -> SectionFilter:
    """Create a filter for DEF 14A proxy statement sections.

    Args:
        sections: List of section keys to filter for. If None, matches all proxy sections.
            Valid keys: executive_compensation, director_compensation, say_on_pay,
            board_composition, audit_committee, related_party, shareholder_proposals,
            beneficial_ownership, equity_compensation
        search_window: Search window size (larger for proxy statements)
        filter_indices: Whether to filter indices

    Returns:
        Configured SectionFilter for proxy statement sections
    """
    if sections is None:
        # Match any proxy section
        section_patterns = list(PROXY_SECTION_PATTERNS.values())
    else:
        section_patterns = [
            PROXY_SECTION_PATTERNS[s]
            for s in sections
            if s in PROXY_SECTION_PATTERNS
        ]

    if not section_patterns:
        raise ValueError(
            f"No valid proxy sections specified. Valid keys: {list(PROXY_SECTION_PATTERNS.keys())}"
        )

    # Combine all patterns into one regex
    combined_pattern = "|".join(f"({p})" for p in section_patterns)

    pattern = SectionPattern(
        section_type=SectionType.CUSTOM,
        custom_pattern=combined_pattern,
    )
    return SectionFilter(
        patterns=[pattern],
        search_window=search_window,
        filter_indices=filter_indices,
    )


# ==================== 13F (Holdings) Filters ====================
def create_holdings_filter(
    include_cover: bool = False,
    search_window: int = 2000,
    filter_indices: bool = True,
) -> SectionFilter:
    """Create a filter for 13F-HR holdings report sections.

    Args:
        include_cover: Whether to include cover page (usually just want info table)
        search_window: Search window size
        filter_indices: Whether to filter indices

    Returns:
        Configured SectionFilter for holdings sections
    """
    patterns_to_use = [HOLDINGS_SECTION_PATTERNS["info_table"]]
    if include_cover:
        patterns_to_use.append(HOLDINGS_SECTION_PATTERNS["cover_page"])
        patterns_to_use.append(HOLDINGS_SECTION_PATTERNS["summary"])

    combined_pattern = "|".join(f"({p})" for p in patterns_to_use)

    pattern = SectionPattern(
        section_type=SectionType.CUSTOM,
        custom_pattern=combined_pattern,
    )
    return SectionFilter(
        patterns=[pattern],
        search_window=search_window,
        filter_indices=filter_indices,
    )
