# module: `sec_nlp/core/stats/` — Statistical Correlation Utilities

## Purpose

A `core` subpackage wrapping `crates/corr` with higher-level helpers for filing-to-market and cross-filing analysis. Provides event study, sector correlation, and cross-filing trend analysis.

## Existing Implementations — Build vs. Reuse

**`scipy.stats`** (PyPI) provides Pearson/Spearman correlation, t-tests, and distributions. The standard Python statistics library. However, it operates on NumPy arrays and is slower than Rust for large batch operations.

**`statsmodels`** (PyPI) provides OLS regression, time series analysis (ARIMA), and event study helpers. Heavy dependency (~50MB installed) with pandas/numpy requirement.

**`eventstudy`** (PyPI) is a lightweight Python event study library implementing MacKinlay (1997) methodology. Limited scope — only event studies, no general correlation.

**Recommendation: Thin Python wrapper around `crates/corr`.** The Rust crate handles the computation-heavy path. This module adds Python-level orchestration: fetching market data, resolving symbols to SIC codes for sector grouping, and assembling result Pydantic models. No need to pull in `scipy` or `statsmodels` — the Rust crate covers the statistical primitives we need.

## File Structure

```
src/sec_nlp/core/stats/
├── __init__.py
├── correlation.py      # Thin wrapper: pearson(), spearman(), rolling_returns(), car(), beta()
├── event_study.py      # Event study orchestration: symbol + date → EventStudyResult
├── sector.py           # Sector correlation matrices by SIC code
└── cross_filing.py     # Cross-filing sentiment/risk trend analysis
```

## Key APIs

### `correlation.py`
Thin wrappers around `crates/corr` PyO3 functions. Lazy-import the `corr` module following the `_load_market_module()` pattern.

```python
def pearson(x: list[float], y: list[float]) -> float: ...
def spearman(x: list[float], y: list[float]) -> float: ...
def cumulative_return(prices: list[float]) -> float | None: ...
def car(asset_prices: list[float], benchmark_prices: list[float]) -> float | None: ...
def beta(asset_returns: list[float], benchmark_returns: list[float]) -> float: ...
def rolling_returns(prices: list[float], window: int) -> list[float]: ...
```

### `event_study.py`
Higher-level orchestration: given a symbol, event date, and benchmark ticker, fetch market data, compute pre/post abnormal returns, and return a structured result.

```python
class EventStudyResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    symbol: str
    event_date: str
    car_pre: float
    car_post: float
    t_stat: float
    p_value: float
    volume_spike: float

def run_event_study(
    symbol: str,
    event_date: str,
    benchmark: str = "SPY",
    pre_window: int = 5,
    post_window: int = 30,
) -> EventStudyResult: ...
```

### `sector.py`
Group symbols by SIC code (from EDGAR metadata), fetch price data, compute intra-sector pairwise correlation matrices.

```python
class SectorCorrelation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    sic_code: str
    symbols: list[str]
    correlation_matrix: dict[str, dict[str, float]]

def sector_correlation(
    symbols: list[str],
    metric: str = "price_return",
    days: int = 252,
) -> list[SectorCorrelation]: ...
```

### `cross_filing.py`
Compare sentiment/risk scores across multiple filings for the same symbol. Detect trend changes.

```python
class FilingTrend(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    symbol: str
    filings: list[str]   # accession numbers
    sentiment_scores: list[float]
    trend_direction: str  # "improving", "declining", "stable"
    inflection_points: list[int]  # indices where trend changes

def cross_filing_trend(
    symbol: str,
    form_type: str = "10-K",
    periods: int = 5,
) -> FilingTrend: ...
```

## Implementation Steps

1. Create `stats/` directory with `__init__.py`.
2. Implement `correlation.py` — lazy import of `corr` module, thin wrappers.
3. Implement `EventStudyResult` Pydantic model.
4. Implement `event_study.py` — fetch market data, call `crates/corr` event_study function.
5. Implement `sector.py` — SIC code grouping, correlation matrix computation.
6. Implement `cross_filing.py` — trend detection from sequential filing analysis results.
7. Write tests: mock `corr` module and market data. Verify orchestration logic. No network.

## Dependencies

- `crates/corr` (via lazy import)
- `sec_nlp.core.market` (existing)
- No new PyPI dependencies
