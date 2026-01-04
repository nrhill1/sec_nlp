"""Shared type aliases for warranty pipeline data structures."""

from __future__ import annotations

from typing import TypedDict


class WarrantyPeriodRecord(TypedDict, total=False):
    symbol: str
    period: str | None
    period_end: str | None
    warranty_liability: float | None
    warranty_payout: float | None
    net_revenue: float | None
    confidence: float | None
    source: str | None
    accession_number: str | None
    xbrl_conflicted_fields: list[str] | None
    warranty_liability_sources: str
    warranty_payout_sources: str
    net_revenue_sources: str


class WarrantyMergeBucket(TypedDict, total=False):
    symbol: str | None
    period: str | None
    period_end: str | None
    warranty_liability: float | None
    warranty_payout: float | None
    net_revenue: float | None
    confidence: float
    source: str | None
    accession_number: str
    warranty_liability_sources: set[str]
    warranty_payout_sources: set[str]
    net_revenue_sources: set[str]
    xbrl_conflicted_fields: set[str]
    _warranty_liability_rank: float
    _warranty_payout_rank: float
    _net_revenue_rank: float
