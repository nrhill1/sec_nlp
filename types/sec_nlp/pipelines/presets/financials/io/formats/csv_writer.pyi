from collections.abc import Mapping
from pathlib import Path

from sec_nlp.types import JsonValue as JsonValue

from ...models import FinancialStatement as FinancialStatement

CSV_COLUMNS: tuple[str, ...]

def write_financials_csv(
    path: Path,
    statements: list[FinancialStatement],
    *,
    header_fields: Mapping[str, JsonValue] | None = None,
) -> None: ...
