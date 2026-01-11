# market

Python extension module built with pyo3 to fetch latest close prices from Yahoo Finance.

## Build (maturin)

maturin develop -m crates/market/Cargo.toml

## Usage

import market

price = market.fetch_price("AAPL")
prices = market.fetch_prices(["AAPL", "MSFT"])
history = market.retrieve_range("AAPL", "2020-01-01..2020-01-31")

Range format: YYYY-MM-DD..YYYY-MM-DD (UTC).
