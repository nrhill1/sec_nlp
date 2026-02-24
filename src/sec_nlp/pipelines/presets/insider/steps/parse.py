# src/sec_nlp/pipelines/presets/insider/steps/parse.py
"""Parsing helpers for insider filing documents."""

from __future__ import annotations

from pathlib import Path

from langchain_core.documents import Document

from sec_nlp.core.edgar.insider_parser import InsiderParser
from sec_nlp.types import JsonValue

from ..models import InsiderTransaction
from .download import DownloadedInsiderFiling


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
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return int(cleaned)
        except ValueError:
            return None
    return None


def _coerce_float(value: JsonValue) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _coerce_roles(value: JsonValue) -> list[str]:
    if not isinstance(value, list):
        return []
    roles: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = item.strip().lower()
        if not cleaned:
            continue
        roles.append(cleaned)
    return sorted(set(roles))


def _source_name(value: JsonValue) -> str | None:
    source = _coerce_str(value)
    if source is None:
        return None
    return Path(source).name


def _tx_date(metadata: dict[str, JsonValue]) -> str | None:
    transaction_date = _coerce_str(metadata.get("transaction_date"))
    if transaction_date is not None:
        return transaction_date
    period_of_report = _coerce_str(metadata.get("period_of_report"))
    if period_of_report is not None:
        return period_of_report
    return _coerce_str(metadata.get("filed_date"))


def _map_document(
    *,
    symbol: str,
    filing: DownloadedInsiderFiling,
    document: Document,
) -> InsiderTransaction:
    metadata = document.metadata

    return InsiderTransaction(
        symbol=symbol,
        accession_number=_coerce_str(metadata.get("accession_number"))
        or filing.accession_number,
        form_type=_coerce_str(metadata.get("document_type"))
        or filing.form_type,
        filed_date=_coerce_str(metadata.get("filed_date")),
        transaction_id=_coerce_str(metadata.get("transaction_id")),
        transaction_index=_coerce_int(metadata.get("transaction_index")),
        transaction_date=_tx_date(metadata),
        owner_name=_coerce_str(metadata.get("reporting_owner_name")),
        owner_cik=_coerce_int(metadata.get("reporting_owner_cik")),
        relationship_roles=_coerce_roles(
            metadata.get("relationship_to_issuer")
        ),
        officer_title=_coerce_str(metadata.get("officer_title")),
        security_title=_coerce_str(metadata.get("security_title")),
        transaction_code=_coerce_str(metadata.get("transaction_code")),
        transaction_type=_coerce_str(metadata.get("transaction_type")),
        ownership_type=_coerce_str(metadata.get("ownership_type")),
        transaction_shares=_coerce_float(metadata.get("transaction_shares")),
        transaction_price=_coerce_float(metadata.get("transaction_price")),
        shares_owned_following_transaction=_coerce_float(
            metadata.get("shares_owned_following_transaction")
        ),
        direct_or_indirect=_coerce_str(metadata.get("direct_or_indirect")),
        source_file=_source_name(metadata.get("source")),
    )


def parse_insider_transactions(
    *,
    symbol: str,
    filing: DownloadedInsiderFiling,
    parser: InsiderParser,
) -> list[InsiderTransaction]:
    """Parse one downloaded filing directory into transactions."""
    docs = parser.parse_accession_dir(filing.filing_dir)

    transactions: list[InsiderTransaction] = []
    for doc in docs:
        transactions.append(
            _map_document(
                symbol=symbol.upper(),
                filing=filing,
                document=doc,
            )
        )

    return transactions
