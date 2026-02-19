// crates/market/src/api.rs
//! Yahoo Finance API operations with caching.

use std::collections::{HashMap, HashSet};

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use yahoo_finance_api::time::{Date, Month, OffsetDateTime};
use yahoo_finance_api::YahooConnector;

use crate::cache::{price_cache, range_cache};
use crate::runtime::run_async;
use crate::types::{to_py_err, MarketQuote};

const QUOTE_RANGE: &str = "1d";
type RangeFetchResult = (String, Result<Vec<MarketQuote>, String>);

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

fn normalize_tickers(tickers: Vec<String>) -> Vec<String> {
    let mut out = Vec::new();
    let mut seen = HashSet::new();
    for raw in tickers {
        let cleaned = raw.trim().to_uppercase();
        if cleaned.is_empty() {
            continue;
        }
        if seen.insert(cleaned.clone()) {
            out.push(cleaned);
        }
    }
    out
}

fn split_cached_ranges(
    tickers: &[String],
    date_range: &str,
) -> (Vec<(String, Vec<MarketQuote>)>, Vec<String>) {
    let mut cached = Vec::new();
    let mut missing = Vec::new();

    for ticker in tickers {
        if let Some(quotes) = range_cache().get(ticker, date_range) {
            cached.push((ticker.clone(), quotes));
        } else {
            missing.push(ticker.clone());
        }
    }

    (cached, missing)
}

fn finalize_partial_ranges(
    fetched: Vec<RangeFetchResult>,
) -> PyResult<Vec<(String, Vec<MarketQuote>)>> {
    let mut successes = Vec::new();
    let mut failures = Vec::new();

    for (ticker, result) in fetched {
        match result {
            Ok(quotes) => successes.push((ticker, quotes)),
            Err(err) => failures.push(format!("{} ({})", ticker, err)),
        }
    }

    if successes.is_empty() && !failures.is_empty() {
        let details = failures.join(", ");
        return Err(PyRuntimeError::new_err(format!(
            "failed to fetch quote ranges for all tickers: {}",
            details
        )));
    }

    Ok(successes)
}

fn fetch_missing_ranges(
    to_fetch: Vec<String>,
    start: OffsetDateTime,
    end: OffsetDateTime,
    start_ts: u64,
    end_ts: u64,
) -> PyResult<Vec<RangeFetchResult>> {
    run_async(async move {
        let provider = YahooConnector::new().map_err(to_py_err)?;
        let mut out = Vec::with_capacity(to_fetch.len());
        for ticker in to_fetch {
            let result = match provider.get_quote_history(&ticker, start, end).await {
                Ok(response) => match response.quotes() {
                    Ok(raw_quotes) => Ok(filter_quotes_by_range(raw_quotes, start_ts, end_ts)),
                    Err(err) => Err(err.to_string()),
                },
                Err(err) => Err(err.to_string()),
            };
            out.push((ticker, result));
        }
        Ok(out)
    })
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

/// Fetch historical quotes for multiple tickers over one date range.
///
/// Reuses one Yahoo connector/session per call and tolerates partial per-ticker
/// failures as long as at least one ticker succeeds.
pub fn get_ranges(
    tickers: Vec<String>,
    date_range: &str,
) -> PyResult<Vec<(String, Vec<MarketQuote>)>> {
    let normalized_tickers = normalize_tickers(tickers);
    if normalized_tickers.is_empty() {
        return Ok(Vec::new());
    }

    let (start, end) = parse_date_range(date_range)?;
    let start_ts = unix_ts(&start)?;
    let end_ts = unix_ts(&end)?;

    let (cached_ranges, to_fetch) = split_cached_ranges(&normalized_tickers, date_range);
    let mut by_ticker: HashMap<String, Vec<MarketQuote>> =
        HashMap::with_capacity(normalized_tickers.len());

    for (ticker, quotes) in cached_ranges {
        by_ticker.insert(ticker, quotes);
    }

    if !to_fetch.is_empty() {
        let fetched = fetch_missing_ranges(to_fetch, start, end, start_ts, end_ts)?;
        let successful_fetches = finalize_partial_ranges(fetched)?;
        for (ticker, quotes) in successful_fetches {
            range_cache().insert(&ticker, date_range, quotes.clone());
            by_ticker.insert(ticker, quotes);
        }
    }

    let mut ordered = Vec::with_capacity(normalized_tickers.len());
    for ticker in normalized_tickers {
        if let Some(quotes) = by_ticker.remove(&ticker) {
            ordered.push((ticker, quotes));
        }
    }
    Ok(ordered)
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

    #[test]
    fn normalize_tickers_dedupes_and_uppercases() {
        let normalized = normalize_tickers(vec![
            " aapl ".to_string(),
            "AAPL".to_string(),
            " msft ".to_string(),
            "".to_string(),
        ]);
        assert_eq!(normalized, vec!["AAPL", "MSFT"]);
    }

    #[test]
    fn split_cached_ranges_mixed_cache_hits() {
        range_cache().clear();
        let date_range = "2024-01-01..2024-01-31";
        let cached_quote = MarketQuote {
            timestamp: 1,
            open: 10.0,
            high: 12.0,
            low: 9.0,
            close: 11.0,
            volume: 1000,
            adjclose: 11.0,
        };
        range_cache().insert("AAPL", date_range, vec![cached_quote.clone()]);

        let tickers = vec!["AAPL".to_string(), "MSFT".to_string()];
        let (cached, missing) = split_cached_ranges(&tickers, date_range);

        assert_eq!(cached.len(), 1);
        assert_eq!(cached[0].0, "AAPL");
        assert_eq!(cached[0].1[0].timestamp, cached_quote.timestamp);
        assert_eq!(missing, vec!["MSFT"]);
    }

    #[test]
    fn finalize_partial_ranges_keeps_successes() {
        let quoted = MarketQuote {
            timestamp: 1,
            open: 1.0,
            high: 1.0,
            low: 1.0,
            close: 1.0,
            volume: 1,
            adjclose: 1.0,
        };
        let fetched = vec![
            ("AAPL".to_string(), Ok(vec![quoted])),
            ("MSFT".to_string(), Err("not found".to_string())),
        ];

        let finalized = finalize_partial_ranges(fetched).unwrap();
        assert_eq!(finalized.len(), 1);
        assert_eq!(finalized[0].0, "AAPL");
    }

    #[test]
    fn finalize_partial_ranges_errors_when_all_fail() {
        let fetched = vec![
            ("AAPL".to_string(), Err("timeout".to_string())),
            ("MSFT".to_string(), Err("not found".to_string())),
        ];
        let err = finalize_partial_ranges(fetched).unwrap_err();
        assert!(err.to_string().contains("failed to fetch quote ranges"));
    }

    #[test]
    fn get_ranges_rejects_invalid_date_range() {
        let err = get_ranges(vec!["AAPL".to_string()], "invalid-range").unwrap_err();
        assert!(err
            .to_string()
            .contains("range must be YYYY-MM-DD..YYYY-MM-DD"));
    }
}
