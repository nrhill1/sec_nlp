from pathlib import Path

from ...models import InsiderTransaction as InsiderTransaction

LEDGER_COLUMNS: tuple[str, ...]

def write_insider_ledger_csv(
    path: Path, transactions: list[InsiderTransaction]
) -> None: ...
