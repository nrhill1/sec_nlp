# src/sec_nlp/pipelines/presets/insider/steps/aggregate.py
"""Aggregation helpers for insider transaction analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..models import InsiderLedger, InsiderTransaction


@dataclass(frozen=True)
class TradeCluster:
    """A short-window cluster of insider transactions."""

    start_date: str
    end_date: str
    unique_owners: int
    transaction_count: int
    owner_names: list[str]
    transaction_ids: list[str]


@dataclass
class _OwnerAccumulator:
    owner_name: str | None
    owner_cik: int | None
    total_transactions: int = 0
    buy_transactions: int = 0
    sell_transactions: int = 0
    net_shares: float = 0.0
    net_value: float = 0.0
    dates: list[date] = field(default_factory=list)


def _parse_iso_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _owner_key(transaction: InsiderTransaction) -> str:
    if transaction.owner_cik is not None:
        return str(transaction.owner_cik)
    if transaction.owner_name:
        return transaction.owner_name.strip().lower()
    return "unknown"


def _direction(transaction: InsiderTransaction) -> int:
    ownership = (transaction.ownership_type or "").strip().upper()
    if ownership == "A":
        return 1
    if ownership == "D":
        return -1

    code = (transaction.transaction_code or "").strip().upper()
    if code in {"P", "A", "M", "C"}:
        return 1
    if code in {"S", "F"}:
        return -1
    return 0


def build_insider_ledgers(
    transactions: list[InsiderTransaction],
) -> list[InsiderLedger]:
    """Aggregate one ledger row per reporting insider."""
    by_owner: dict[str, _OwnerAccumulator] = {}

    for transaction in transactions:
        owner_key = _owner_key(transaction)
        row = by_owner.get(owner_key)
        if row is None:
            row = _OwnerAccumulator(
                owner_name=transaction.owner_name,
                owner_cik=transaction.owner_cik,
            )
            by_owner[owner_key] = row

        row.total_transactions += 1

        direction = _direction(transaction)
        shares = transaction.transaction_shares or 0.0
        value = transaction.transaction_value or 0.0

        if direction > 0:
            row.buy_transactions += 1
        elif direction < 0:
            row.sell_transactions += 1

        row.net_shares += direction * shares
        row.net_value += direction * value

        tx_date = _parse_iso_date(transaction.transaction_date)
        if tx_date is not None:
            row.dates.append(tx_date)

        if row.owner_name is None and transaction.owner_name:
            row.owner_name = transaction.owner_name
        if row.owner_cik is None and transaction.owner_cik is not None:
            row.owner_cik = transaction.owner_cik

    ledger_rows: list[InsiderLedger] = []
    for owner_key, row in by_owner.items():
        first_date = min(row.dates).isoformat() if row.dates else None
        last_date = max(row.dates).isoformat() if row.dates else None

        ledger_rows.append(
            InsiderLedger(
                owner_key=owner_key,
                owner_name=row.owner_name,
                owner_cik=row.owner_cik,
                total_transactions=row.total_transactions,
                buy_transactions=row.buy_transactions,
                sell_transactions=row.sell_transactions,
                net_shares=row.net_shares,
                net_value=row.net_value,
                first_transaction_date=first_date,
                last_transaction_date=last_date,
            )
        )

    return sorted(
        ledger_rows,
        key=lambda item: (
            abs(item.net_value),
            item.total_transactions,
            item.owner_key,
        ),
        reverse=True,
    )


def compute_net_buy_ratio(
    transactions: list[InsiderTransaction],
) -> float | None:
    """Compute normalized buy-vs-sell ratio over all transactions."""
    if not transactions:
        return None

    buys = 0
    sells = 0
    for transaction in transactions:
        direction = _direction(transaction)
        if direction > 0:
            buys += 1
        elif direction < 0:
            sells += 1

    total = buys + sells
    if total == 0:
        return None
    return (buys - sells) / total


def find_trade_clusters(
    transactions: list[InsiderTransaction],
    *,
    window_days: int,
    cluster_threshold: int,
) -> list[TradeCluster]:
    """Find windows where many unique insiders traded close together."""
    indexed: list[tuple[date, InsiderTransaction]] = []
    for transaction in transactions:
        tx_date = _parse_iso_date(transaction.transaction_date)
        if tx_date is None:
            continue
        indexed.append((tx_date, transaction))

    indexed.sort(key=lambda item: item[0])
    clusters: list[TradeCluster] = []
    seen_signatures: set[tuple[str, ...]] = set()

    for start_idx, (start_date, _) in enumerate(indexed):
        end_idx = start_idx
        while end_idx < len(indexed):
            candidate_date = indexed[end_idx][0]
            if (candidate_date - start_date).days > window_days:
                break
            end_idx += 1

        window = indexed[start_idx:end_idx]
        if not window:
            continue

        owners: dict[str, str] = {}
        transaction_ids: list[str] = []
        for _, tx in window:
            owner_key = _owner_key(tx)
            owner_name = tx.owner_name or owner_key
            owners[owner_key] = owner_name
            if tx.transaction_id:
                transaction_ids.append(tx.transaction_id)

        if len(owners) < cluster_threshold:
            continue

        signature = tuple(sorted(transaction_ids))
        if signature and signature in seen_signatures:
            continue
        if signature:
            seen_signatures.add(signature)

        cluster_end = window[-1][0].isoformat()
        clusters.append(
            TradeCluster(
                start_date=start_date.isoformat(),
                end_date=cluster_end,
                unique_owners=len(owners),
                transaction_count=len(window),
                owner_names=sorted(owners.values()),
                transaction_ids=sorted(transaction_ids),
            )
        )

    return clusters


def transaction_direction(transaction: InsiderTransaction) -> int:
    """Expose direction classification for downstream correlation logic."""
    return _direction(transaction)
