# src/sec_nlp/pipelines/presets/financials/steps/aggregate.py
"""Aggregation helpers for financial statement facts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sec_nlp.types import JsonValue

from ..models import FinancialFact, FinancialStatement


@dataclass(frozen=True)
class FinancialDelta:
    """Delta payload for a single financial metric."""

    current: float | None
    previous: float | None
    absolute_change: float | None
    percent_change: float | None


def _safe_ratio(
    numerator: float | None, denominator: float | None
) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    return numerator / denominator


def _choose_value(current: float | None, candidate: float) -> float:
    if current is None:
        return candidate
    return candidate if abs(candidate) >= abs(current) else current


def _period_key(fact: FinancialFact) -> str:
    return (
        fact.period_end
        or fact.period_instant
        or fact.period_start
        or fact.accession_number
    )


def aggregate_financials(
    facts: Iterable[FinancialFact],
    *,
    compute_ratios: bool = True,
) -> list[FinancialStatement]:
    """Pivot normalized facts into per-period financial statement rows."""
    rows: dict[str, dict[str, float | str | None]] = {}

    for fact in facts:
        period = _period_key(fact)
        row = rows.setdefault(
            period,
            {"period": period, "accession_number": fact.accession_number},
        )
        existing = row.get(fact.concept)
        existing_float = (
            existing if isinstance(existing, (int, float)) else None
        )
        row[fact.concept] = _choose_value(existing_float, fact.value)
        if not row.get("accession_number"):
            row["accession_number"] = fact.accession_number

    statements: list[FinancialStatement] = []
    for period in sorted(rows.keys(), reverse=True):
        row = rows[period]
        statement = FinancialStatement(
            period=period,
            accession_number=str(row.get("accession_number") or "") or None,
            revenue=_as_float(row.get("revenue")),
            net_income=_as_float(row.get("net_income")),
            eps_basic=_as_float(row.get("eps_basic")),
            eps_diluted=_as_float(row.get("eps_diluted")),
            total_assets=_as_float(row.get("total_assets")),
            total_liabilities=_as_float(row.get("total_liabilities")),
            stockholders_equity=_as_float(row.get("stockholders_equity")),
            cash_and_cash_equivalents=_as_float(
                row.get("cash_and_cash_equivalents")
            ),
            long_term_debt=_as_float(row.get("long_term_debt")),
            operating_income=_as_float(row.get("operating_income")),
            gross_profit=_as_float(row.get("gross_profit")),
            current_assets=_as_float(row.get("current_assets")),
            current_liabilities=_as_float(row.get("current_liabilities")),
        )
        if compute_ratios:
            statement = statement.model_copy(
                update={
                    "current_ratio": _safe_ratio(
                        statement.current_assets, statement.current_liabilities
                    ),
                    "debt_to_equity": _safe_ratio(
                        statement.total_liabilities,
                        statement.stockholders_equity,
                    ),
                    "gross_margin": _safe_ratio(
                        statement.gross_profit, statement.revenue
                    ),
                    "operating_margin": _safe_ratio(
                        statement.operating_income, statement.revenue
                    ),
                    "roe": _safe_ratio(
                        statement.net_income, statement.stockholders_equity
                    ),
                }
            )
        statements.append(statement)

    return statements


def _as_float(value: JsonValue) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def build_delta_report(
    statements: list[FinancialStatement],
) -> dict[str, FinancialDelta]:
    """Build metric deltas between latest and previous periods."""
    if len(statements) < 2:
        return {}

    latest = statements[0]
    previous = statements[1]
    tracked_metrics = (
        "revenue",
        "net_income",
        "eps_basic",
        "eps_diluted",
        "total_assets",
        "total_liabilities",
        "stockholders_equity",
        "cash_and_cash_equivalents",
        "long_term_debt",
        "operating_income",
        "gross_profit",
        "current_assets",
        "current_liabilities",
        "current_ratio",
        "debt_to_equity",
        "gross_margin",
        "operating_margin",
        "roe",
    )

    report: dict[str, FinancialDelta] = {}
    for metric in tracked_metrics:
        current = getattr(latest, metric)
        prior = getattr(previous, metric)
        absolute_change = (
            None if current is None or prior is None else current - prior
        )
        percent_change = (
            None
            if absolute_change is None or prior in (None, 0)
            else absolute_change / prior
        )
        report[metric] = FinancialDelta(
            current=current,
            previous=prior,
            absolute_change=absolute_change,
            percent_change=percent_change,
        )

    return report
