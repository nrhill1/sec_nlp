from pydantic import BaseModel as BaseModel

from sec_nlp.core.market import MarketRetriever as MarketRetriever

class EconomicDataError(RuntimeError): ...

class EconomicSeries(BaseModel):
    series_id: str
    description: str
    observations: list[tuple[str, float]]

class MacroContext(BaseModel):
    filing_date: str
    gdp_growth: float | None
    cpi_yoy: float | None
    unemployment_rate: float | None
    fed_funds_rate: float | None
    yield_spread_10y_2y: float | None

class MacroSensitivity(BaseModel):
    symbol: str
    indicator_id: str
    correlation: float
    p_value: float
    window_days: int

def fetch_series(
    series_id: str,
    start_date: str = ...,
    end_date: str = ...,
) -> EconomicSeries: ...
def align_to_filings(
    series: EconomicSeries,
    filing_dates: list[str],
) -> list[MacroContext]: ...
def compute_macro_sensitivity(
    symbol: str,
    indicator_id: str,
    window_days: int = ...,
    *,
    retriever: MarketRetriever | None = ...,
) -> MacroSensitivity: ...
