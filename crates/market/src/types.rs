// crates/market/src/types.rs
//! Type definitions for market data.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

/// Market quote data.
#[derive(Debug, Clone)]
pub struct MarketQuote {
    pub timestamp: u64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: u64,
    pub adjclose: f64,
}

impl MarketQuote {
    /// Convert from yahoo_finance_api Quote.
    pub fn from_yahoo(quote: yahoo_finance_api::Quote) -> Self {
        Self {
            timestamp: quote.timestamp,
            open: quote.open,
            high: quote.high,
            low: quote.low,
            close: quote.close,
            volume: quote.volume,
            adjclose: quote.adjclose,
        }
    }

    /// Convert to Python dict.
    pub fn to_py_dict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let dict = PyDict::new(py);
        dict.set_item("timestamp", self.timestamp)?;
        dict.set_item("open_price", self.open)?;
        dict.set_item("high", self.high)?;
        dict.set_item("low", self.low)?;
        dict.set_item("close", self.close)?;
        dict.set_item("volume", self.volume)?;
        dict.set_item("adjclose", self.adjclose)?;
        Ok(dict)
    }
}

/// Cached price entry with timestamp.
#[derive(Debug, Clone)]
pub struct CachedPrice {
    pub price: f64,
    pub cached_at: std::time::Instant,
}

/// Cached quote range entry.
#[derive(Debug, Clone)]
pub struct CachedQuotes {
    pub quotes: Vec<MarketQuote>,
    pub cached_at: std::time::Instant,
}

/// Helper to convert any error to PyErr.
pub fn to_py_err<E: std::fmt::Display>(err: E) -> PyErr {
    PyRuntimeError::new_err(err.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn market_quote_from_yahoo() {
        let yahoo_quote = yahoo_finance_api::Quote {
            timestamp: 1234567890,
            open: 100.0,
            high: 110.0,
            low: 95.0,
            close: 105.0,
            volume: 1000000,
            adjclose: 104.5,
        };
        let quote = MarketQuote::from_yahoo(yahoo_quote);
        assert_eq!(quote.timestamp, 1234567890);
        assert_eq!(quote.close, 105.0);
    }
}
