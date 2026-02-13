"""CSV writer for financial statement rows."""

from __future__ import annotations

import csv
from pathlib import Path

from ...models import FinancialStatement

CSV_COLUMNS: tuple[str, ...] = (
    "period",
    "accession_number",
    "revenue",
    "net_income",
    "eps_basic",
    "eps_diluted",
    "total_assets",
    "total_liabilities",
    "stockholders_equity",
    "cash_and_cash_equivalents",
    "long_term_debt",
    "operating_income",
    "gross_profit",
    "current_assets",
    "current_liabilities",
    "current_ratio",
    "debt_to_equity",
    "gross_margin",
    "operating_margin",
    "roe",
)


def write_financials_csv(
    path: Path, statements: list[FinancialStatement]
) -> None:
    """Write per-period financial statement rows to CSV."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        for statement in statements:
            payload = statement.model_dump(mode="json")
            row = {column: payload.get(column) for column in CSV_COLUMNS}
            writer.writerow(row)
