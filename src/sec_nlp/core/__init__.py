# src/sec_nlp/core/__init__.py
"""Core functionality for sec-nlp."""

from .edgar.filing_mode import FilingMode
from .infra.logger import LogContext, logger, setup_logging
from .ingest.exhibit_downloader import (
    ExhibitDocument,
    ExhibitDownloader,
    create_exhibit_downloader,
)
from .ingest.loader import Loader
from .text.filters import (
    HOLDINGS_SECTION_PATTERNS,
    PROXY_SECTION_PATTERNS,
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
from .text.section_extractor import (
    ExtractedSection,
    SectionBoundary,
    SectionExtractor,
    create_section_extractor,
)

__all__: tuple[str, ...] = (
    # Core
    "Loader",
    # Enums
    "FilingMode",
    # Exhibit Downloading
    "ExhibitDownloader",
    "ExhibitDocument",
    "create_exhibit_downloader",
    # Filters
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
    # Section Extraction
    "SectionExtractor",
    "ExtractedSection",
    "SectionBoundary",
    "create_section_extractor",
    # Logging
    "LogContext",
    "logger",
    "setup_logging",
)
