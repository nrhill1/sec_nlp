// crates/market/src/lib.rs
//! Python extension module for market data.
//!
//! Provides cached access to Yahoo Finance API via PyO3.

mod api;
mod cache;
mod runtime;
mod types;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyModule};

use api::{get_price, get_prices, get_range, get_ranges};

/// Fetch the latest price for a single ticker.
///
/// Results are cached for 5 minutes to reduce API calls.
#[pyfunction]
fn fetch_price(ticker: &str) -> PyResult<f64> {
    get_price(ticker)
}

/// Fetch latest prices for multiple tickers.
///
/// Returns a dict mapping ticker -> price.
/// Results are cached for 5 minutes.
#[pyfunction]
fn fetch_prices(py: Python<'_>, tickers: Vec<String>) -> PyResult<PyObject> {
    let prices = get_prices(tickers)?;
    let dict = PyDict::new(py);
    for (ticker, price) in prices {
        dict.set_item(ticker, price)?;
    }
    Ok(dict.into())
}

/// Fetch historical quotes for a date range.
///
/// Args:
///     ticker: Stock ticker symbol
///     date_range: Date range as "YYYY-MM-DD..YYYY-MM-DD" or "YYYY-MM-DD,YYYY-MM-DD"
///
/// Returns a list of quote dicts with keys:
///     timestamp, open_price, high, low, close, volume, adjclose
#[pyfunction]
fn retrieve_range(py: Python<'_>, ticker: &str, date_range: &str) -> PyResult<PyObject> {
    let quotes = get_range(ticker, date_range)?;
    let list = PyList::empty(py);
    for quote in quotes {
        list.append(quote.to_py_dict(py)?)?;
    }
    Ok(list.into())
}

/// Fetch historical quotes for multiple tickers for one date range.
///
/// Returns a dict mapping ticker -> list of quote dicts.
#[pyfunction]
fn retrieve_ranges(py: Python<'_>, tickers: Vec<String>, date_range: &str) -> PyResult<PyObject> {
    let ranges = get_ranges(tickers, date_range)?;
    let dict = PyDict::new(py);
    for (ticker, quotes) in ranges {
        let list = PyList::empty(py);
        for quote in quotes {
            list.append(quote.to_py_dict(py)?)?;
        }
        dict.set_item(ticker, list)?;
    }
    Ok(dict.into())
}

/// Clear all cached market data.
#[pyfunction]
fn clear_cache() {
    cache::price_cache().clear();
    cache::range_cache().clear();
}

#[pymodule]
fn market(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(fetch_price, m)?)?;
    m.add_function(wrap_pyfunction!(fetch_prices, m)?)?;
    m.add_function(wrap_pyfunction!(retrieve_range, m)?)?;
    m.add_function(wrap_pyfunction!(retrieve_ranges, m)?)?;
    m.add_function(wrap_pyfunction!(clear_cache, m)?)?;
    Ok(())
}
