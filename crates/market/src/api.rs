// crates/market/src/api.rs
//! Yahoo Finance API operations with caching.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use yahoo_finance_api::time::{Date, Month, OffsetDateTime};
use yahoo_finance_api::YahooConnector;

use crate::cache::{price_cache, range_cache};
use crate::runtime::run_async;
use crate::types::{to_py_err, MarketQuote};

const QUOTE_RANGE: &str = "1d";

/// Parse a date string (YYYY-MM-DD) to OffsetDateTime.
pub fn parse_date(value: &str) -> PyResult<OffsetDateTime> {
    let mut parts = value.trim().split('-');
    let year = parts
        .next()
        .ok_or_else(|| PyValueError::new_err("range must include start date"))?
        .parse::<i32>()
        .map_err(|_| PyValueError::new_err("invalid year in range"))?;
    let month = parts
        .next()
        .ok_or_else(|| PyValueError::new_err("range must include month"))?
        .parse::<u8>()
        .map_err(|_| PyValueError::new_err("invalid month in range"))?;
    let day = parts
        .next()
        .ok_or_else(|| PyValueError::new_err("range must include day"))?
        .parse::<u8>()
        .map_err(|_| PyValueError::new_err("invalid day in range"))?;
    if parts.next().is_some() {
        return Err(PyValueError::new_err(
            "date must be formatted as YYYY-MM-DD",
        ));
    }

    let month = Month::try_from(month).map_err(|_| PyValueError::new_err("month must be 1-12"))?;
    let date = Date::from_calendar_date(year, month, day)
        .map_err(|_| PyValueError::new_err("invalid date"))?;
    Ok(date.midnight().assume_utc())
}

/// Parse date range string (YYYY-MM-DD..YYYY-MM-DD or YYYY-MM-DD,YYYY-MM-DD).
pub fn parse_date_range(date_range: &str) -> PyResult<(OffsetDateTime, OffsetDateTime)> {
    let (start_raw, end_raw) = date_range
        .split_once("..")
        .or_else(|| date_range.split_once(','))
        .ok_or_else(|| PyValueError::new_err("range must be YYYY-MM-DD..YYYY-MM-DD"))?;
    let start = parse_date(start_raw)?;
    let end = parse_date(end_raw)?;
    if end < start {
        return Err(PyValueError::new_err("range end must be >= start"));
    }
    Ok((start, end))
}

/// Convert OffsetDateTime to unix timestamp.
pub fn unix_ts(dt: &OffsetDateTime) -> PyResult<u64> {
    let ts = dt.unix_timestamp();
    if ts < 0 {
        return Err(PyValueError::new_err(
            "range must be on or after 1970-01-01",
        ));
    }
    Ok(ts as u64)
}

/// Filter quotes by timestamp range (inclusive).
pub fn filter_quotes_by_range(
    quotes: Vec<yahoo_finance_api::Quote>,
    start_ts: u64,
    end_ts: u64,
) -> Vec<MarketQuote> {
    quotes
        .into_iter()
        .filter(|q| q.timestamp >= start_ts && q.timestamp <= end_ts)
        .map(MarketQuote::from_yahoo)
        .collect()
}

/// Fetch latest price for a single ticker (with caching).
pub fn get_price(ticker: &str) -> PyResult<f64> {
    // Check cache first
    if let Some(price) = price_cache().get(ticker) {
        return Ok(price);
    }

    // Fetch from API
    let ticker_owned = ticker.to_string();
    let price = run_async(async move {
        let provider = YahooConnector::new().map_err(to_py_err)?;
        let response = provider
            .get_latest_quotes(&ticker_owned, QUOTE_RANGE)
            .await
            .map_err(to_py_err)?;
        let quote = response.last_quote().map_err(to_py_err)?;
        Ok(quote.close)
    })?;

    // Cache the result
    price_cache().insert(ticker.to_string(), price);
    Ok(price)
}

/// Fetch latest prices for multiple tickers (with caching).
pub fn get_prices(tickers: Vec<String>) -> PyResult<Vec<(String, f64)>> {
    let mut results = Vec::with_capacity(tickers.len());
    let mut to_fetch = Vec::new();

    // Check cache for each ticker
    for ticker in &tickers {
        if let Some(price) = price_cache().get(ticker) {
            results.push((ticker.clone(), price));
        } else {
            to_fetch.push(ticker.clone());
        }
    }

    // Fetch missing from API
    if !to_fetch.is_empty() {
        let fetched = run_async(async move {
            let provider = YahooConnector::new().map_err(to_py_err)?;
            let mut out = Vec::with_capacity(to_fetch.len());
            for ticker in to_fetch {
                let response = provider
                    .get_latest_quotes(&ticker, QUOTE_RANGE)
                    .await
                    .map_err(to_py_err)?;
                let quote = response.last_quote().map_err(to_py_err)?;
                out.push((ticker, quote.close));
            }
            Ok(out)
        })?;

        // Cache and add to results
        for (ticker, price) in fetched {
            price_cache().insert(ticker.clone(), price);
            results.push((ticker, price));
        }
    }

    Ok(results)
}

/// Fetch historical quotes for a date range (with caching).
pub fn get_range(ticker: &str, date_range: &str) -> PyResult<Vec<MarketQuote>> {
    // Check cache first
    if let Some(quotes) = range_cache().get(ticker, date_range) {
        return Ok(quotes);
    }

    // Parse and fetch
    let (start, end) = parse_date_range(date_range)?;
    let start_ts = unix_ts(&start)?;
    let end_ts = unix_ts(&end)?;

    let ticker_owned = ticker.to_string();
    let quotes = run_async(async move {
        let provider = YahooConnector::new().map_err(to_py_err)?;
        let response = provider
            .get_quote_history(&ticker_owned, start, end)
            .await
            .map_err(to_py_err)?;
        let raw_quotes = response.quotes().map_err(to_py_err)?;
        Ok(filter_quotes_by_range(raw_quotes, start_ts, end_ts))
    })?;

    // Cache the result
    range_cache().insert(ticker, date_range, quotes.clone());
    Ok(quotes)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_date_valid() {
        let dt = parse_date("2020-01-05").unwrap();
        assert_eq!(dt.date().year(), 2020);
        assert_eq!(dt.date().month(), Month::January);
        assert_eq!(dt.date().day(), 5);
    }

    #[test]
    fn parse_date_invalid_month() {
        assert!(parse_date("2020-13-01").is_err());
    }

    #[test]
    fn parse_date_invalid_format() {
        assert!(parse_date("2020-01").is_err());
        assert!(parse_date("2020-01-01-01").is_err());
    }

    #[test]
    fn parse_date_range_dotdot() {
        let (start, end) = parse_date_range("2020-01-01..2020-01-31").unwrap();
        assert!(end >= start);
    }

    #[test]
    fn parse_date_range_comma() {
        let (start, end) = parse_date_range("2020-01-01,2020-01-31").unwrap();
        assert!(end >= start);
    }

    #[test]
    fn parse_date_range_reversed() {
        assert!(parse_date_range("2020-01-31..2020-01-01").is_err());
    }

    #[test]
    fn unix_ts_rejects_pre_epoch() {
        let date = Date::from_calendar_date(1969, Month::December, 31).unwrap();
        let dt = date.midnight().assume_utc();
        assert!(unix_ts(&dt).is_err());
    }

    #[test]
    fn filter_quotes_inclusive() {
        let quotes = vec![
            yahoo_finance_api::Quote {
                timestamp: 5,
                open: 0.0,
                high: 0.0,
                low: 0.0,
                close: 0.0,
                volume: 0,
                adjclose: 0.0,
            },
            yahoo_finance_api::Quote {
                timestamp: 10,
                open: 0.0,
                high: 0.0,
                low: 0.0,
                close: 0.0,
                volume: 0,
                adjclose: 0.0,
            },
            yahoo_finance_api::Quote {
                timestamp: 15,
                open: 0.0,
                high: 0.0,
                low: 0.0,
                close: 0.0,
                volume: 0,
                adjclose: 0.0,
            },
            yahoo_finance_api::Quote {
                timestamp: 21,
                open: 0.0,
                high: 0.0,
                low: 0.0,
                close: 0.0,
                volume: 0,
                adjclose: 0.0,
            },
        ];
        let filtered = filter_quotes_by_range(quotes, 10, 20);
        let timestamps: Vec<u64> = filtered.iter().map(|q| q.timestamp).collect();
        assert_eq!(timestamps, vec![10, 15]);
    }
}
