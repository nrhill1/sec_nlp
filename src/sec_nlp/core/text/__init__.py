# src/sec_nlp/core/text/__init__.py
"""Text processing helpers for SEC filings."""

from .chunking import SentenceSplitter
from .deduplication import SimHashConfig, SimHashDeduplicator
from .filters import (
    SectionFilter,
    SectionPattern,
    SectionType,
    create_default_section_filter,
    create_exhibit_filter,
    create_holdings_filter,
    create_item_filter,
    create_multi_section_filter,
    create_proxy_filter,
)
from .keyword import (
    FilterStats,
    KeywordHit,
    KeywordMatcher,
    KeywordScore,
    KeywordSpec,
)
from .section_extractor import (
    ExtractedSection,
    SectionBoundary,
    SectionExtractor,
    create_section_extractor,
)
from .section_patterns import (
    HOLDINGS_SECTION_PATTERNS,
    PROXY_SECTION_PATTERNS,
    REGISTRATION_SECTION_PATTERNS,
)

__all__ = (
    "SentenceSplitter",
    "SimHashConfig",
    "SimHashDeduplicator",
    "SectionFilter",
    "SectionPattern",
    "SectionType",
    "create_default_section_filter",
    "create_exhibit_filter",
    "create_holdings_filter",
    "create_item_filter",
    "create_multi_section_filter",
    "create_proxy_filter",
    "PROXY_SECTION_PATTERNS",
    "HOLDINGS_SECTION_PATTERNS",
    "REGISTRATION_SECTION_PATTERNS",
    "FilterStats",
    "KeywordHit",
    "KeywordMatcher",
    "KeywordScore",
    "KeywordSpec",
    "SectionExtractor",
    "ExtractedSection",
    "SectionBoundary",
    "create_section_extractor",
)
