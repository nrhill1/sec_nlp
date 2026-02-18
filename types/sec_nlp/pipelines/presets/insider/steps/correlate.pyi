from ..config import InsiderSettings as InsiderSettings
from ..models import (
    InsiderAlert as InsiderAlert,
    InsiderTransaction as InsiderTransaction,
)
from .aggregate import TradeCluster as TradeCluster

def correlate_insider_activity(
    *,
    symbol: str,
    transactions: list[InsiderTransaction],
    clusters: list[TradeCluster],
    settings: InsiderSettings,
) -> tuple[list[InsiderAlert], dict[str, int]]: ...
