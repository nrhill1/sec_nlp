# market

Python extension module built with pyo3 to fetch latest close prices from Yahoo Finance.

## Build (maturin)

maturin develop -m crates/market/Cargo.toml

## Usage

import market

price = market.fetch_price("AAPL")
prices = market.fetch_prices(["AAPL", "MSFT"])
