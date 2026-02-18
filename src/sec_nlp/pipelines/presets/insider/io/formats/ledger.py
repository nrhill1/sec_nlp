"""CSV writer for insider transaction ledger exports."""

from __future__ import annotations

import csv
from collections.abc import Mapping
from pathlib import Path

from sec_nlp.pipelines.output_io import write_csv_metadata_comments
from sec_nlp.types import JsonValue

from ...models import InsiderTransaction

LEDGER_COLUMNS: tuple[str, ...] = (
    "symbol",
    "accession_number",
    "form_type",
    "filed_date",
    "transaction_id",
    "transaction_index",
    "transaction_date",
    "owner_name",
    "owner_cik",
    "relationship_roles",
    "officer_title",
    "security_title",
    "transaction_code",
    "transaction_type",
    "ownership_type",
    "transaction_shares",
    "transaction_price",
    "transaction_value",
    "shares_owned_following_transaction",
    "direct_or_indirect",
    "source_file",
)


def write_insider_ledger_csv(
    path: Path,
    transactions: list[InsiderTransaction],
    *,
    header_fields: Mapping[str, JsonValue] | None = None,
) -> None:
    """Write one CSV row per insider transaction."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        write_csv_metadata_comments(handle, header_fields)
        writer = csv.DictWriter(handle, fieldnames=list(LEDGER_COLUMNS))
        writer.writeheader()
        for transaction in transactions:
            payload = transaction.model_dump(mode="json")
            payload["relationship_roles"] = ",".join(
                transaction.relationship_roles
            )
            payload["transaction_value"] = transaction.transaction_value
            row = {column: payload.get(column) for column in LEDGER_COLUMNS}
            writer.writerow(row)
