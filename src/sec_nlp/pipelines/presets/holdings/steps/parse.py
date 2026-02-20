"""Parsing helpers for 13F holdings filings."""

from __future__ import annotations

from pathlib import Path

from langchain_core.documents import Document

from sec_nlp.core.edgar.holdings_parser import HoldingsParser
from sec_nlp.types import JsonValue

from ..models import HoldingPosition
from .download import DownloadedHoldingsFiling


def _coerce_str(value: JsonValue) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _coerce_int(value: JsonValue) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if not cleaned:
            return None
        try:
            return int(float(cleaned))
        except ValueError:
            return None
    return None


def _source_name(value: JsonValue) -> str | None:
    source = _coerce_str(value)
    if source is None:
        return None
    return Path(source).name


def _map_document(
    *,
    symbol: str,
    filing: DownloadedHoldingsFiling,
    document: Document,
) -> HoldingPosition:
    metadata = document.metadata
    voting_authority = metadata.get("voting_authority")
    voting = voting_authority if isinstance(voting_authority, dict) else {}

    return HoldingPosition(
        symbol=symbol,
        accession_number=_coerce_str(metadata.get("accession_number"))
        or filing.accession_number,
        form_type=_coerce_str(metadata.get("form_type")) or filing.form_type,
        filed_date=_coerce_str(metadata.get("filed_date")),
        holding_index=_coerce_int(metadata.get("holding_index")),
        issuer=_coerce_str(metadata.get("issuer")),
        title_of_class=_coerce_str(metadata.get("title_of_class")),
        cusip=_coerce_str(metadata.get("cusip")),
        value_thousands=_coerce_int(metadata.get("value")),
        shares=_coerce_int(metadata.get("shares")),
        share_type=_coerce_str(metadata.get("share_type")),
        investment_discretion=_coerce_str(
            metadata.get("investment_discretion")
        ),
        other_manager=_coerce_str(metadata.get("other_manager")),
        voting_sole=_coerce_int(voting.get("sole")),
        voting_shared=_coerce_int(voting.get("shared")),
        voting_none=_coerce_int(voting.get("none")),
        source_file=_source_name(metadata.get("source")),
    )


def parse_holding_positions(
    *,
    symbol: str,
    filing: DownloadedHoldingsFiling,
    parser: HoldingsParser,
    cusip_filter: str | None = None,
) -> list[HoldingPosition]:
    """Parse one downloaded holdings filing directory into positions."""
    docs = parser.parse_accession_dir(filing.filing_dir)

    positions: list[HoldingPosition] = []
    normalized_filter = cusip_filter.strip().upper() if cusip_filter else None
    for doc in docs:
        position = _map_document(
            symbol=symbol.upper(),
            filing=filing,
            document=doc,
        )
        if normalized_filter and position.cusip != normalized_filter:
            continue
        positions.append(position)

    return positions
