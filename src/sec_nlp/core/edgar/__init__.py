# src/sec_nlp/core/edgar/__init__.py
"""EDGAR/SEC-specific domain helpers."""

from __future__ import annotations

import warnings

# Suppress the runpy warning when running this module as __main__
# This occurs when using: python -m sec_nlp.core.edgar.efts
warnings.filterwarnings(
    "ignore",
    category=RuntimeWarning,
    message=r"'sec_nlp\.core\.edgar\.efts' found in sys\.modules.*",
)


def __getattr__(name: str) -> object:
    """Lazy load EFTS modules to avoid import issues when running as __main__."""
    efts_exports = {
        "EFTSAPIError": "efts",
        "EFTSClient": "efts",
        "EFTSClientConfig": "efts",
        "create_efts_client": "efts",
        "EFTSError": "efts_models",
        "EFTSHit": "efts_models",
        "EFTSSearchParams": "efts_models",
        "EFTSSearchResponse": "efts_models",
        "EFTSSortField": "efts_models",
        "EFTSSortOrder": "efts_models",
    }

    other_exports = {
        "FilingMode": "filing_mode",
        "HoldingsParser": "holdings_parser",
        "parse_holdings_documents": "holdings_parser",
        "InsiderParser": "insider_parser",
        "parse_insider_documents": "insider_parser",
        "RelationshipResolver": "relationship_resolver",
        "build_related_filings_map": "relationship_resolver",
        "serialize_relationship_graph": "relationship_resolver",
        "FilingIdentifier": "relationships",
        "FilingRelation": "relationships",
        "FilingRelationshipGraph": "relationships",
        "FilingRelationType": "relationships",
        "XbrlExtensionError": "xbrl_facts",
        "XbrlFact": "xbrl_facts",
        "XbrlParser": "xbrl_facts",
        "create_xbrl_parser": "xbrl_facts",
        "extract_facts": "xbrl_facts",
        "extract_facts_from_file": "xbrl_facts",
    }

    all_exports = {**efts_exports, **other_exports}
    if name not in all_exports:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name = all_exports[name]
    from importlib import import_module

    module = import_module(f".{module_name}", __name__)
    return getattr(module, name)


__all__ = (
    "create_efts_client",
    "EFTSAPIError",
    "EFTSClient",
    "EFTSClientConfig",
    "EFTSError",
    "EFTSHit",
    "EFTSSearchParams",
    "EFTSSearchResponse",
    "EFTSSortField",
    "EFTSSortOrder",
    "FilingIdentifier",
    "FilingMode",
    "FilingRelation",
    "FilingRelationshipGraph",
    "FilingRelationType",
    "HoldingsParser",
    "InsiderParser",
    "RelationshipResolver",
    "build_related_filings_map",
    "parse_holdings_documents",
    "parse_insider_documents",
    "serialize_relationship_graph",
    "XbrlExtensionError",
    "XbrlFact",
    "XbrlParser",
    "create_xbrl_parser",
    "extract_facts",
    "extract_facts_from_file",
)

# Enable lazy loading via __getattr__
__lazy__ = True
