from ..models import (
    HoldingPosition as HoldingPosition,
    OwnershipSummary as OwnershipSummary,
)

def build_ownership_summary(
    *,
    symbol: str,
    positions: list[HoldingPosition],
    top_holders: int,
    cusip_filter: str | None = None,
) -> OwnershipSummary: ...
