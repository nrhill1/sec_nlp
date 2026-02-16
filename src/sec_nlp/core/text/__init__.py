# src/sec_nlp/core/text/__init__.py
"""Text processing helpers for SEC filings."""

from .chunking import SentenceSplitter
from .deduplication import SimHashConfig, SimHashDeduplicator
from .entity_extraction import (
    Entity,
    EntityExtensionError,
    EventMention,
    detect_events,
    enrich_documents,
    extract_entities,
)
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
from .risk_factors import (
    RiskFactorClusterConfig,
    build_risk_factor_clusters,
    cluster_risk_factors,
    dedupe_risk_factor_statements,
    extract_risk_factor_statements,
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
    "EntityExtensionError",
    "Entity",
    "EventMention",
    "extract_entities",
    "detect_events",
    "enrich_documents",
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
    "RiskFactorClusterConfig",
    "extract_risk_factor_statements",
    "dedupe_risk_factor_statements",
    "cluster_risk_factors",
    "build_risk_factor_clusters",
    "SectionExtractor",
    "ExtractedSection",
    "SectionBoundary",
    "create_section_extractor",
)
