from collections.abc import Mapping
from pathlib import Path

from sec_nlp.types import JsonValue as JsonValue

from ...models import HoldingPosition as HoldingPosition

SNAPSHOT_COLUMNS: tuple[str, ...]

def write_holdings_snapshot_csv(
    path: Path,
    positions: list[HoldingPosition],
    *,
    header_fields: Mapping[str, JsonValue] | None = None,
) -> None: ...
