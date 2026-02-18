# market

Rust/PyO3 extension used by `sec_nlp.core.market` and the `sec-nlp market` command.

## Capabilities
- `fetch_price(symbol)` - latest close price
- `fetch_prices([symbols...])` - latest close prices for multiple tickers
- `retrieve_range(symbol, "YYYY-MM-DD..YYYY-MM-DD")` - OHLCV(+adjclose) range

## Build

```bash
maturin develop -m crates/market/Cargo.toml
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
```

Range format is inclusive and uses `YYYY-MM-DD..YYYY-MM-DD`.
