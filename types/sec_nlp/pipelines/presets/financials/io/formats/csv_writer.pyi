from pathlib import Path

from ...models import FinancialStatement as FinancialStatement

CSV_COLUMNS: tuple[str, ...]

def write_financials_csv(
    path: Path, statements: list[FinancialStatement]
) -> None: ...
