# crate: `crates/corr` — Statistical Correlation Engine

## Purpose

Consolidate the ad-hoc statistical calculations scattered across the Python codebase (cumulative returns in `market_correlation.py`, pstdev calls, volume spike ratios) into a single, tested Rust engine. Exposes functions to Python via PyO3.

## Existing Implementations — Build vs. Reuse

**`ta-statistics`** (crates.io) provides 25+ rolling-window statistical functions for time series including correlation, beta, volatility, skewness, and kurtosis. Finance-oriented with `PairedStatistics` for paired time series. However, it is streaming/rolling-window focused — it processes one value at a time, not batch vectors.

**`statrs`** (crates.io) provides probability distributions, hypothesis testing (t-tests), and basic descriptive statistics. Mature and well-maintained.

**`timeseries`** (crates.io) provides slicing, rolling windows, resampling, correlation, and ARIMA. Early-stage, unstable API.

**Recommendation: Custom crate using `statrs` as a dependency.** The existing crates lack the specific combination needed: batch vector correlation + cumulative abnormal returns + event-study windowing + PyO3 export. Use `statrs` for distributions and p-values in the event-study t-test, but implement the financial-specific functions (CAR, beta, rolling returns, Garman-Klass) directly — they are straightforward `f64` math that doesn't warrant pulling in a full framework. `ta-statistics` is worth noting as an alternative if rolling/streaming mode is later needed.

## Existing Code to Study

- `src/sec_nlp/pipelines/presets/analyze/io/formats/market_correlation.py` — `_compute_cumulative_return()`, `_compute_returns()`, `_compute_volume_spike()`, `_compute_net_sentiment()`. These are the calculations this crate replaces.
- `src/sec_nlp/pipelines/presets/analyze/market.py` — `_aggregate_quotes()`, `_bucket_key()`. Aggregation logic that feeds the correlation layer.
- `crates/market/src/lib.rs` — reference for simple PyO3 function exports.

## File Structure

```
crates/corr/
├── Cargo.toml
├── Makefile
├── build.rs
├── src/
│   ├── lib.rs            # PyO3 module: register all functions
│   ├── correlation.rs    # Pearson, Spearman rank correlation
│   ├── returns.rs        # Simple returns, log returns, cumulative returns, CAR
│   ├── volatility.rs     # Std dev, average true range, Garman-Klass
│   ├── beta.rs           # Beta vs. benchmark series
│   ├── event_study.rs    # Pre/post window splitting, t-test on means
│   ├── util.rs           # Shared helpers: mean, rank, sort
│   └── error.rs          # CorrError type
└── tests/
    ├── test_correlation.rs
    ├── test_returns.rs
    ├── test_volatility.rs
    └── test_event_study.rs
```

## Key Function Signatures

```rust
// correlation.rs
#[pyfunction]
fn pearson(x: Vec<f64>, y: Vec<f64>) -> PyResult<f64>;

#[pyfunction]
fn spearman(x: Vec<f64>, y: Vec<f64>) -> PyResult<f64>;

// returns.rs
#[pyfunction]
fn simple_returns(prices: Vec<f64>) -> PyResult<Vec<f64>>;

#[pyfunction]
fn cumulative_return(prices: Vec<f64>) -> PyResult<Option<f64>>;

/// Cumulative abnormal return: asset returns minus benchmark returns.
#[pyfunction]
fn car(asset_prices: Vec<f64>, benchmark_prices: Vec<f64>) -> PyResult<Option<f64>>;

#[pyfunction]
fn rolling_returns(prices: Vec<f64>, window: usize) -> PyResult<Vec<f64>>;

// volatility.rs
#[pyfunction]
fn std_dev(values: Vec<f64>) -> PyResult<f64>;

#[pyfunction]
fn garman_klass(high: Vec<f64>, low: Vec<f64>, open: Vec<f64>, close: Vec<f64>) -> PyResult<f64>;

// beta.rs
#[pyfunction]
fn beta(asset_returns: Vec<f64>, benchmark_returns: Vec<f64>) -> PyResult<f64>;

// event_study.rs
#[pyfunction]
fn event_study(
    prices: Vec<f64>,
    timestamps: Vec<i64>,
    event_timestamp: i64,
    pre_window: i64,   // days before event
    post_window: i64,  // days after event
) -> PyResult<EventStudyResult>;
```

## Dependencies (Cargo.toml)

```toml
[dependencies]
pyo3 = { version = "0.23", features = ["extension-module"] }
statrs = "0.18"    # Normal distribution, t-distribution for p-values
```

`ndarray` is optional — only add if matrix correlation (N×N) is needed.

## Implementation Steps

1. **Scaffold the crate.** Copy boilerplate from `crates/efts/`. `crate-type = ["cdylib"]`. Minimal `lib.rs` with `#[pymodule]`.

2. **Implement `util.rs`.** Mean, variance, rank (for Spearman). Pure Rust, no dependencies beyond std.

3. **Implement `correlation.rs`.** Pearson: standard formula using mean/variance. Spearman: rank the inputs, then apply Pearson to ranks. Return `Err` if series lengths differ or are < 2.

4. **Implement `returns.rs`.** `simple_returns`: `(p[i] / p[i-1]) - 1.0`. `cumulative_return`: `(last / first) - 1.0`. `car`: difference of cumulative returns. `rolling_returns`: sliding window of cumulative returns.

5. **Implement `volatility.rs`.** Population std dev. Garman-Klass estimator from OHLC data. Average true range.

6. **Implement `beta.rs`.** OLS slope of asset returns regressed on benchmark returns: `cov(a, b) / var(b)`.

7. **Implement `event_study.rs`.** Split price series into pre/post windows around an event timestamp. Compute CAR for each window. Run a two-sample t-test (using `statrs::distribution::StudentsT`) on pre vs. post returns. Return `EventStudyResult { car_pre, car_post, t_stat, p_value }`.

8. **Register all functions in `lib.rs`.** Add `m.add_function(wrap_pyfunction!(...))` for each exported function.

9. **Add to root Makefile.** `CORR_DIR`, `CORR_MANIFEST`, `rs-corr-%` target, include in `build-ext`.

10. **Write Python wrapper** (`src/sec_nlp/core/stats/correlation.py`). Thin wrappers: `pearson()`, `spearman()`, `car()`, `beta()`, `event_study()`. Lazy-import the `corr` module. Follow the `_load_market_module()` pattern from `src/sec_nlp/core/market.py`.

11. **Migrate `market_correlation.py`.** Replace `_compute_cumulative_return()`, `_compute_returns()`, `_compute_volume_spike()` with calls to the `corr` crate wrappers. Keep the Python functions as thin adapters.

12. **Add type stubs** (`types/corr/__init__.pyi`).

13. **Write tests.** Rust: known-answer tests (precomputed correlation values, returns). Python: mock the extension, test the wrapper layer. No network.

## Testing Strategy

- Rust tests use hardcoded f64 vectors with known statistical properties (e.g., perfectly correlated series → r=1.0, uncorrelated → r≈0.0).
- Edge cases: empty vectors, single-element vectors, all-zero vectors, NaN handling.
- Python tests mock the `corr` module and verify adapter functions pass correct arguments.
