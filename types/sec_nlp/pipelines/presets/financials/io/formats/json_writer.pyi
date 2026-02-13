from pathlib import Path

from pydantic import BaseModel

from sec_nlp.types import JsonValue as JsonValue

from ...models import FinancialStatement as FinancialStatement
from ...steps.aggregate import FinancialDelta as FinancialDelta

class FinancialsOutputPayload(BaseModel):
    symbol: str
    filings_processed: int
    periods: list[FinancialStatement]
    delta_report: dict[str, FinancialDelta]
    metadata: dict[str, JsonValue]

def write_financials_json(
    path: Path, payload: FinancialsOutputPayload
) -> None: ...
def write_financials_yaml(
    path: Path, payload: FinancialsOutputPayload
) -> None: ...
