from ..models import (
    HoldingPosition as HoldingPosition,
    HoldingsDiff as HoldingsDiff,
)

def build_holdings_diffs(
    *,
    symbol: str,
    positions: list[HoldingPosition],
) -> list[HoldingsDiff]: ...
