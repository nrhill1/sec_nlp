from dataclasses import dataclass

from ..models import (
    InsiderLedger as InsiderLedger,
    InsiderTransaction as InsiderTransaction,
)

@dataclass(frozen=True)
class TradeCluster:
    start_date: str
    end_date: str
    unique_owners: int
    transaction_count: int
    owner_names: list[str]
    transaction_ids: list[str]

def build_insider_ledgers(
    transactions: list[InsiderTransaction],
) -> list[InsiderLedger]: ...
def compute_net_buy_ratio(
    transactions: list[InsiderTransaction],
) -> float | None: ...
def find_trade_clusters(
    transactions: list[InsiderTransaction],
    *,
    window_days: int,
    cluster_threshold: int,
) -> list[TradeCluster]: ...
def transaction_direction(transaction: InsiderTransaction) -> int: ...
