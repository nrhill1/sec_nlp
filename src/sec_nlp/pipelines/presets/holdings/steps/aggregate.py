# src/sec_nlp/pipelines/presets/holdings/steps/aggregate.py
"""Aggregate ownership metrics for holdings pipeline."""

from __future__ import annotations

from datetime import date

from ..models import HoldingPosition, OwnershipSummary, TopHolding


def _parse_iso_date(value: str | None) -> date:
    """Parse ISO-formatted date strings safely."""
    if value is None:
        return date.min
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date.min


def _latest_accession_positions(
    positions: list[HoldingPosition],
) -> tuple[str | None, str | None, list[HoldingPosition]]:
    """Select latest accession positions for each holding key."""
    if not positions:
        return None, None, []

    by_accession: dict[str, list[HoldingPosition]] = {}
    for position in positions:
        by_accession.setdefault(position.accession_number, []).append(position)

    latest_accession = max(
        by_accession,
        key=lambda accession: (
            _parse_iso_date(by_accession[accession][0].filed_date),
            accession,
        ),
    )
    latest_positions = by_accession[latest_accession]
    latest_date = latest_positions[0].filed_date
    return latest_accession, latest_date, latest_positions


def _normalize_latest_snapshot(
    positions: list[HoldingPosition],
) -> list[TopHolding]:
    """Normalize latest holdings snapshot rows for output."""
    by_cusip: dict[str, TopHolding] = {}
    for position in positions:
        if not position.cusip:
            continue
        current = by_cusip.get(position.cusip)
        shares = position.shares or 0
        value = position.value_thousands or 0

        if current is None:
            by_cusip[position.cusip] = TopHolding(
                cusip=position.cusip,
                issuer=position.issuer,
                shares=shares,
                value_thousands=value,
            )
            continue

        by_cusip[position.cusip] = TopHolding(
            cusip=position.cusip,
            issuer=position.issuer or current.issuer,
            shares=current.shares + shares,
            value_thousands=current.value_thousands + value,
        )

    return list(by_cusip.values())


def _compute_hhi(holdings: list[TopHolding]) -> float | None:
    """Compute HHI concentration score from position weights."""
    total_value = sum(holding.value_thousands for holding in holdings)
    if total_value <= 0:
        return None

    hhi = 0.0
    for holding in holdings:
        weight = holding.value_thousands / total_value
        hhi += (weight * 100) ** 2
    return hhi


def build_ownership_summary(
    *,
    symbol: str,
    positions: list[HoldingPosition],
    top_holders: int,
    cusip_filter: str | None = None,
) -> OwnershipSummary:
    """Build latest-quarter ownership concentration summary."""
    latest_accession, latest_date, latest_positions = (
        _latest_accession_positions(positions)
    )

    normalized_snapshot = _normalize_latest_snapshot(latest_positions)
    total_value = sum(
        holding.value_thousands for holding in normalized_snapshot
    )
    total_shares = sum(holding.shares for holding in normalized_snapshot)

    sorted_holdings: list[TopHolding] = sorted(
        normalized_snapshot,
        key=lambda holding: (
            holding.value_thousands,
            holding.shares,
            holding.cusip,
        ),
        reverse=True,
    )

    top_items: list[TopHolding] = []
    for holding in sorted_holdings[:top_holders]:
        weight = (
            (holding.value_thousands / total_value) if total_value > 0 else None
        )
        top_items.append(
            holding.model_copy(update={"portfolio_weight": weight})
        )

    normalized_filter = cusip_filter.strip().upper() if cusip_filter else None
    filtered_rows = (
        [
            holding
            for holding in normalized_snapshot
            if holding.cusip == normalized_filter
        ]
        if normalized_filter
        else normalized_snapshot
    )

    return OwnershipSummary(
        symbol=symbol,
        latest_accession=latest_accession,
        latest_filed_date=latest_date,
        total_positions=len(normalized_snapshot),
        unique_cusips=len(normalized_snapshot),
        total_shares=total_shares,
        total_value_thousands=total_value,
        concentration_hhi=_compute_hhi(normalized_snapshot),
        top_holdings=top_items,
        cusip_filter=normalized_filter,
        filtered_positions=len(filtered_rows),
        filtered_total_shares=sum(item.shares for item in filtered_rows),
        filtered_total_value_thousands=sum(
            item.value_thousands for item in filtered_rows
        ),
    )
