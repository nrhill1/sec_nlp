from collections.abc import Mapping
from pathlib import Path

from sec_nlp.types import JsonValue as JsonValue

from ...models import InsiderTransaction as InsiderTransaction

LEDGER_COLUMNS: tuple[str, ...]

def write_insider_ledger_csv(
    path: Path,
    transactions: list[InsiderTransaction],
    *,
    header_fields: Mapping[str, JsonValue] | None = None,
) -> None: ...
