# module: `sec_nlp/core/edgar/economic.py` — Economic Indicator Integration

## Purpose

Fetch macroeconomic time series from the FRED API and align them with filing and market data for contextual analysis. Enables the `--macro-context` flag in the analyze pipeline.

## Existing Implementations — Build vs. Reuse

**`fredapi`** (PyPI, `mortada/fredapi`) is the official Python client for the FRED API. Provides `Fred.get_series()` returning pandas Series. Mature, 4K+ GitHub stars, minimal dependencies (pandas, requests). MIT licensed.

**`full_fred`** (PyPI) is another FRED client with async support and caching. Less mature than `fredapi`.

**`pandas-datareader`** (PyPI) can pull FRED data among other sources. However, it is a heavier dependency and the FRED support is a subset of what `fredapi` provides.

**Recommendation: Use `fredapi` as a dependency.** It is the standard, well-maintained FRED client and avoids reimplementing HTTP calls and series parsing. Wrap it in a thin adapter that:
1. Manages API key configuration (via environment variable, consistent with existing config patterns).
2. Converts pandas Series to plain `list[tuple[str, float]]` to avoid leaking pandas into the core model layer.
3. Adds filing-date alignment and macro-sensitivity computation using `crates/corr`.

## File Structure

```
src/sec_nlp/core/edgar/economic.py   # Single file module
```

## Key APIs

```python
class EconomicSeries(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    series_id: str              # e.g., "GDP", "CPIAUCSL", "UNRATE"
    description: str
    observations: list[tuple[str, float]]  # (date_str, value) pairs

class MacroContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    filing_date: str
    gdp_growth: float | None = None
    cpi_yoy: float | None = None
    unemployment_rate: float | None = None
    fed_funds_rate: float | None = None
    yield_spread_10y_2y: float | None = None

class MacroSensitivity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    symbol: str
    indicator_id: str
    correlation: float
    p_value: float
    window_days: int


def fetch_series(series_id: str, start_date: str = "", end_date: str = "") -> EconomicSeries:
    """Fetch a FRED time series. Wraps fredapi.Fred.get_series()."""
    ...

def align_to_filings(
    series: EconomicSeries,
    filing_dates: list[str],
) -> list[MacroContext]:
    """Map each filing date to the nearest available economic observation."""
    ...

def compute_macro_sensitivity(
    symbol: str,
    indicator_id: str,
    window_days: int = 252,
) -> MacroSensitivity:
    """Correlation between a stock's returns and a macro indicator."""
    ...
```

## Implementation Details

- FRED API key configured via `FRED_API_KEY` environment variable. Raise a clear error if not set.
- `fetch_series()` wraps `fredapi.Fred(api_key=...).get_series(series_id)`, converts the pandas Series to `list[tuple[str, float]]`.
- `align_to_filings()` uses binary search to find the nearest observation date for each filing date. Returns `MacroContext` with the standard indicators populated.
- `compute_macro_sensitivity()` fetches both the stock's returns (via `sec_nlp.core.market`) and the indicator series, then calls `crates/corr` `pearson()` with the aligned values.

## Implementation Steps

- [x] Add `fredapi` to `pyproject.toml` dependencies.
- [x] Implement `EconomicSeries`, `MacroContext`, `MacroSensitivity` Pydantic models.
- [x] Implement `fetch_series()` — wrap fredapi, convert to plain types.
- [x] Implement `align_to_filings()` — binary search alignment.
- [x] Implement `compute_macro_sensitivity()` — fetch data, compute correlation.
- [x] Add `--macro-context` flag to the analyze pipeline config.
- [x] Write tests: mock `fredapi.Fred`, verify alignment logic and correlation pass-through. No network.

## Dependencies

- `fredapi` (new PyPI dependency — add to pyproject.toml)
- `crates/corr` (via `sec_nlp.core.stats.correlation`)
- `sec_nlp.core.market` (existing)
