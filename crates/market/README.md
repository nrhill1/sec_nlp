# market

Rust/PyO3 extension used by `sec_nlp.core.market`, Pulse refresh, and retained
specialist market analysis.

## Capabilities
- `fetch_price(symbol)` - latest close price
- `fetch_prices([symbols...])` - latest close prices for multiple tickers
- `retrieve_range(symbol, "YYYY-MM-DD..YYYY-MM-DD")` - OHLCV(+adjclose) range
- `retrieve_ranges([symbols...], "YYYY-MM-DD..YYYY-MM-DD")` - batched OHLCV(+adjclose) ranges using one Yahoo session per call
- `MarketSession().retrieve_range_async(symbol, range)` - awaitable fresh quotes
  using a reusable Yahoo connection pool

## Build

```bash
maturin develop
```

Or from the repo root:

```bash
make build-ext
```

## Python usage

```python
import market

latest = market.fetch_price("AAPL")
latest_batch = market.fetch_prices(["AAPL", "MSFT"])
history = market.retrieve_range("AAPL", "2025-01-01..2025-01-31")
history_batch = market.retrieve_ranges(
    ["AAPL", "MSFT"],
    "2025-01-01..2025-01-31",
)
```

Range format is inclusive and uses `YYYY-MM-DD..YYYY-MM-DD`.

The synchronous functions release Python's interpreter lock while fetching and
retain their five-minute cache. An explicitly created `MarketSession` performs
no network requests until its async method is awaited. Async requests bypass
cache reads and update the cache after success, allowing manual refresh to check
the provider immediately. Cancellation drops the native request future; an
enforced twenty-second deadline bounds an individual native request.
After cancellation, the Python adapter awaits `wait_idle_async()` so native
requests have actually released their resources before the workspace records a
cancelled job. This waits for active requests on the shared session to finish.
The adapter pauses admission of new requests during cleanup and shields the
native acknowledgement from repeated cancellation, so queued symbols cannot
extend that cleanup indefinitely.

`MarketRetriever.retrieve_range_async` adapts native quote dictionaries to
`MarketQuote` records. Pulse shares one retriever across four concurrent market
and news operations and applies a twenty-second total source deadline, including
at most one retry for connection/read failures, HTTP 429, or HTTP 5xx. Provider
status codes survive the native error boundary so permanent failures are not
retried. Existing synchronous specialist behavior is preserved.
