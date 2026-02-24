# src/sec_nlp/pipelines/presets/holdings/steps/diff.py
"""Quarter-over-quarter diff logic for holdings pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from ..models import HoldingPosition, HoldingsDiff


@dataclass(frozen=True)
class _SnapshotPosition:
    cusip: str
    issuer: str | None
    shares: int
    value_thousands: int


def _parse_iso_date(value: str | None) -> date:
    if value is None:
        return date.min
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date.min


def _snapshot_for_accession(
    positions: list[HoldingPosition],
) -> dict[str, _SnapshotPosition]:
    snapshot: dict[str, _SnapshotPosition] = {}
    for position in positions:
        if not position.cusip:
            continue
        current = snapshot.get(position.cusip)

        shares = position.shares or 0
        value = position.value_thousands or 0

        if current is None:
            snapshot[position.cusip] = _SnapshotPosition(
                cusip=position.cusip,
                issuer=position.issuer,
                shares=shares,
                value_thousands=value,
            )
            continue

        snapshot[position.cusip] = _SnapshotPosition(
            cusip=position.cusip,
            issuer=position.issuer or current.issuer,
            shares=current.shares + shares,
            value_thousands=current.value_thousands + value,
        )

    return snapshot


def _diff_status(
    previous: int, current: int
) -> Literal["increase", "decrease", "unchanged"]:
    if current > previous:
        return "increase"
    if current < previous:
        return "decrease"
    return "unchanged"


def build_holdings_diffs(
    *,
    symbol: str,
    positions: list[HoldingPosition],
) -> list[HoldingsDiff]:
    """Build consecutive-quarter holdings diffs keyed by CUSIP."""
    by_accession: dict[str, list[HoldingPosition]] = {}
    for position in positions:
        by_accession.setdefault(position.accession_number, []).append(position)

    ordered_accessions = sorted(
        by_accession,
        key=lambda accession: (
            _parse_iso_date(by_accession[accession][0].filed_date),
            accession,
        ),
    )
    if len(ordered_accessions) < 2:
        return []

    diffs: list[HoldingsDiff] = []
    for previous_accession, current_accession in zip(
        ordered_accessions,
        ordered_accessions[1:],
        strict=False,
    ):
        previous_positions = by_accession[previous_accession]
        current_positions = by_accession[current_accession]
        previous_snapshot = _snapshot_for_accession(previous_positions)
        current_snapshot = _snapshot_for_accession(current_positions)

        previous_date = previous_positions[0].filed_date
        current_date = current_positions[0].filed_date

        for cusip in sorted(set(previous_snapshot) | set(current_snapshot)):
            prev = previous_snapshot.get(cusip)
            curr = current_snapshot.get(cusip)

            if prev is None and curr is not None:
                diffs.append(
                    HoldingsDiff(
                        symbol=symbol,
                        cusip=cusip,
                        issuer=curr.issuer,
                        status="new",
                        previous_accession=previous_accession,
                        current_accession=current_accession,
                        previous_filed_date=previous_date,
                        current_filed_date=current_date,
                        previous_shares=0,
                        current_shares=curr.shares,
                        share_change=curr.shares,
                        previous_value_thousands=0,
                        current_value_thousands=curr.value_thousands,
                        value_change_thousands=curr.value_thousands,
                    )
                )
                continue

            if prev is not None and curr is None:
                diffs.append(
                    HoldingsDiff(
                        symbol=symbol,
                        cusip=cusip,
                        issuer=prev.issuer,
                        status="exit",
                        previous_accession=previous_accession,
                        current_accession=current_accession,
                        previous_filed_date=previous_date,
                        current_filed_date=current_date,
                        previous_shares=prev.shares,
                        current_shares=0,
                        share_change=-prev.shares,
                        previous_value_thousands=prev.value_thousands,
                        current_value_thousands=0,
                        value_change_thousands=-prev.value_thousands,
                    )
                )
                continue

            if prev is None or curr is None:
                continue

            share_change = curr.shares - prev.shares
            value_change = curr.value_thousands - prev.value_thousands
            diffs.append(
                HoldingsDiff(
                    symbol=symbol,
                    cusip=cusip,
                    issuer=curr.issuer or prev.issuer,
                    status=_diff_status(prev.shares, curr.shares),
                    previous_accession=previous_accession,
                    current_accession=current_accession,
                    previous_filed_date=previous_date,
                    current_filed_date=current_date,
                    previous_shares=prev.shares,
                    current_shares=curr.shares,
                    share_change=share_change,
                    previous_value_thousands=prev.value_thousands,
                    current_value_thousands=curr.value_thousands,
                    value_change_thousands=value_change,
                )
            )

    return diffs
