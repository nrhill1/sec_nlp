"""CSV writer for holdings snapshot exports."""

from __future__ import annotations

import csv
from collections.abc import Mapping
from pathlib import Path

from sec_nlp.pipelines.output_io import write_csv_metadata_comments
from sec_nlp.types import JsonValue

from ...models import HoldingPosition

SNAPSHOT_COLUMNS: tuple[str, ...] = (
    "symbol",
    "accession_number",
    "form_type",
    "filed_date",
    "holding_index",
    "issuer",
    "title_of_class",
    "cusip",
    "value_thousands",
    "shares",
    "share_type",
    "investment_discretion",
    "other_manager",
    "voting_sole",
    "voting_shared",
    "voting_none",
    "source_file",
)


def write_holdings_snapshot_csv(
    path: Path,
    positions: list[HoldingPosition],
    *,
    header_fields: Mapping[str, JsonValue] | None = None,
) -> None:
    """Write one CSV row per normalized holding position."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        write_csv_metadata_comments(handle, header_fields)
        writer = csv.DictWriter(handle, fieldnames=list(SNAPSHOT_COLUMNS))
        writer.writeheader()
        for position in positions:
            payload = position.model_dump(mode="json")
            row = {column: payload.get(column) for column in SNAPSHOT_COLUMNS}
            writer.writerow(row)
