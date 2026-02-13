from typing import ClassVar, Literal

from pydantic import BaseModel

from sec_nlp.pipelines import BasePipelineResult as BasePipelineResult
from sec_nlp.types import JsonValue as JsonValue

class FinancialFact(BaseModel):
    symbol: str
    accession_number: str
    form_type: str
    concept: str
    raw_tag: str
    value: float
    unit: str | None
    decimals: int | None
    period_start: str | None
    period_end: str | None
    period_instant: str | None
    segment: str | None
    source_file: str | None

class FinancialStatement(BaseModel):
    period: str
    accession_number: str | None
    revenue: float | None
    net_income: float | None
    eps_basic: float | None
    eps_diluted: float | None
    total_assets: float | None
    total_liabilities: float | None
    stockholders_equity: float | None
    cash_and_cash_equivalents: float | None
    long_term_debt: float | None
    operating_income: float | None
    gross_profit: float | None
    current_assets: float | None
    current_liabilities: float | None
    current_ratio: float | None
    debt_to_equity: float | None
    gross_margin: float | None
    operating_margin: float | None
    roe: float | None

class FinancialsResult(BasePipelineResult):
    pipeline_type: ClassVar[Literal["financials"]]
    symbols_processed: int
    periods_generated: int
    def summary_fields(self) -> dict[str, JsonValue]: ...
