from collections.abc import Iterable
from dataclasses import dataclass

from ..models import (
    FinancialFact as FinancialFact,
    FinancialStatement as FinancialStatement,
)

@dataclass(frozen=True)
class FinancialDelta:
    current: float | None
    previous: float | None
    absolute_change: float | None
    percent_change: float | None

def aggregate_financials(
    facts: Iterable[FinancialFact], *, compute_ratios: bool = ...
) -> list[FinancialStatement]: ...
def build_delta_report(
    statements: list[FinancialStatement],
) -> dict[str, FinancialDelta]: ...
