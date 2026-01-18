# src/sec_nlp/core/edgar/__init__.py
"""EDGAR/SEC-specific domain helpers."""

from .efts import (
    EFTSAPIError,
    EFTSClient,
    EFTSClientConfig,
    create_efts_client,
)
from .efts_models import (
    EFTSError,
    EFTSHit,
    EFTSSearchParams,
    EFTSSearchResponse,
    EFTSSortField,
    EFTSSortOrder,
)
from .filing_mode import FilingMode
from .holdings_parser import HoldingsParser, parse_holdings_documents
from .insider_parser import InsiderParser, parse_insider_documents
from .relationship_resolver import (
    RelationshipResolver,
    build_related_filings_map,
    serialize_relationship_graph,
)
from .relationships import (
    FilingIdentifier,
    FilingRelation,
    FilingRelationshipGraph,
    FilingRelationType,
)

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
)
