use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyModule};
use std::future::Future;
use yahoo_finance_api::time::{Date, Month, OffsetDateTime};
use yahoo_finance_api::{Quote, YahooConnector};

const QUOTE_RANGE: &str = "1d";

fn to_py_err<E: std::fmt::Display>(err: E) -> PyErr {
    PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(err.to_string())
}

fn run_async<T>(future: impl Future<Output = PyResult<T>>) -> PyResult<T> {
    let runtime = tokio::runtime::Runtime::new().map_err(to_py_err)?;
    runtime.block_on(future)
}

fn parse_date(value: &str) -> PyResult<OffsetDateTime> {
    let mut parts = value.trim().split('-');
    let year = parts
        .next()
        .ok_or_else(|| PyErr::new::<PyValueError, _>("range must include start date"))?
        .parse::<i32>()
        .map_err(|_| PyErr::new::<PyValueError, _>("invalid year in range"))?;
    let month = parts
        .next()
        .ok_or_else(|| PyErr::new::<PyValueError, _>("range must include month"))?
        .parse::<u8>()
        .map_err(|_| PyErr::new::<PyValueError, _>("invalid month in range"))?;
    let day = parts
        .next()
        .ok_or_else(|| PyErr::new::<PyValueError, _>("range must include day"))?
        .parse::<u8>()
        .map_err(|_| PyErr::new::<PyValueError, _>("invalid day in range"))?;
    if parts.next().is_some() {
        return Err(PyErr::new::<PyValueError, _>(
            "date must be formatted as YYYY-MM-DD",
        ));
    }

    let month = Month::try_from(month)
        .map_err(|_| PyErr::new::<PyValueError, _>("month must be 1-12"))?;
    let date = Date::from_calendar_date(year, month, day)
        .map_err(|_| PyErr::new::<PyValueError, _>("invalid date"))?;
    Ok(date.midnight().assume_utc())
}

fn retrieve_range_bounds(
    date_range: &str,
) -> PyResult<(OffsetDateTime, OffsetDateTime)> {
    let (start_raw, end_raw) = date_range
        .split_once("..")
        .or_else(|| date_range.split_once(','))
        .ok_or_else(|| {
            PyErr::new::<PyValueError, _>("range must be YYYY-MM-DD..YYYY-MM-DD")
        })?;
    let start = parse_date(start_raw)?;
    let end = parse_date(end_raw)?;
    if end < start {
        return Err(PyErr::new::<PyValueError, _>(
            "range end must be >= start",
        ));
    }
    Ok((start, end))
}

fn unix_ts(dt: &OffsetDateTime) -> PyResult<u64> {
    let ts = dt.unix_timestamp();
    if ts < 0 {
        return Err(PyErr::new::<PyValueError, _>(
            "range must be on or after 1970-01-01",
        ));
    }
    Ok(ts as u64)
}

fn quote_to_object(py: Python<'_>, quote: Quote) -> PyResult<PyObject> {
    let dict = PyDict::new(py);
    dict.set_item("timestamp", quote.timestamp)?;
    dict.set_item("open_price", quote.open)?;
    dict.set_item("high", quote.high)?;
    dict.set_item("low", quote.low)?;
    dict.set_item("close", quote.close)?;
    dict.set_item("volume", quote.volume)?;
    dict.set_item("adjclose", quote.adjclose)?;
    Ok(dict.into())
}

fn filter_quotes_by_range(
    quotes: Vec<Quote>,
    start_ts: u64,
    end_ts: u64,
) -> Vec<Quote> {
    quotes
        .into_iter()
        .filter(|quote| quote.timestamp >= start_ts && quote.timestamp <= end_ts)
        .collect()
}

async fn fetch_price_async(ticker: String) -> PyResult<f64> {
    let provider = YahooConnector::new().map_err(to_py_err)?;
    let response = provider
        .get_latest_quotes(&ticker, QUOTE_RANGE)
        .await
        .map_err(to_py_err)?;
    let quote = response.last_quote().map_err(to_py_err)?;
    Ok(quote.close)
}

async fn fetch_prices_async(tickers: Vec<String>) -> PyResult<Vec<(String, f64)>> {
    let provider = YahooConnector::new().map_err(to_py_err)?;
    let mut out = Vec::with_capacity(tickers.len());
    for ticker in tickers {
        let response = provider
            .get_latest_quotes(&ticker, QUOTE_RANGE)
            .await
            .map_err(to_py_err)?;
        let quote = response.last_quote().map_err(to_py_err)?;
        out.push((ticker, quote.close));
    }
    Ok(out)
}

async fn fetch_range_async(
    ticker: String,
    date_range: String,
) -> PyResult<Vec<Quote>> {
    let (start, end) = retrieve_range_bounds(&date_range)?;
    let start_ts = unix_ts(&start)?;
    let end_ts = unix_ts(&end)?;
    let provider = YahooConnector::new().map_err(to_py_err)?;
    let response = provider
        .get_quote_history(&ticker, start, end)
        .await
        .map_err(to_py_err)?;
    let quotes = response.quotes().map_err(to_py_err)?;
    Ok(filter_quotes_by_range(quotes, start_ts, end_ts))
}

#[pyfunction]
fn fetch_price(ticker: &str) -> PyResult<f64> {
    run_async(fetch_price_async(ticker.to_string()))
}

#[pyfunction]
fn fetch_prices(py: Python<'_>, tickers: Vec<String>) -> PyResult<PyObject> {
    let prices = run_async(fetch_prices_async(tickers))?;
    let dict = PyDict::new(py);
    for (ticker, price) in prices {
        dict.set_item(ticker, price)?;
    }
    Ok(dict.into())
}

#[pyfunction]
fn retrieve_range(
    py: Python<'_>,
    ticker: &str,
    date_range: &str,
) -> PyResult<PyObject> {
    let quotes = run_async(fetch_range_async(
        ticker.to_string(),
        date_range.to_string(),
    ))?;
    let list = PyList::empty(py);
    for quote in quotes {
        list.append(quote_to_object(py, quote)?)?;
    }
    Ok(list.into())
}

#[pymodule]
fn market(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(fetch_price, m)?)?;
    m.add_function(wrap_pyfunction!(fetch_prices, m)?)?;
    m.add_function(wrap_pyfunction!(retrieve_range, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_quote(timestamp: u64) -> Quote {
        Quote {
            timestamp,
            open: 0.0,
            high: 0.0,
            low: 0.0,
            close: 0.0,
            volume: 0,
            adjclose: 0.0,
        }
    }

    #[test]
    fn parse_date_accepts_valid() {
        let dt = parse_date("2020-01-05").unwrap();
        let date = dt.date();
        assert_eq!(date.year(), 2020);
        assert_eq!(date.month(), Month::January);
        assert_eq!(date.day(), 5);
        assert_eq!(dt.time().hour(), 0);
        assert_eq!(dt.time().minute(), 0);
        assert_eq!(dt.time().second(), 0);
    }

    #[test]
    fn parse_date_rejects_invalid() {
        assert!(parse_date("2020-13-01").is_err());
        assert!(parse_date("2020-01").is_err());
        assert!(parse_date("2020-02-30").is_err());
    }

    #[test]
    fn retrieve_range_bounds_accepts_dotdot() {
        let (start, end) =
            retrieve_range_bounds("2020-01-01..2020-01-02").unwrap();
        assert!(end >= start);
    }

    #[test]
    fn retrieve_range_bounds_accepts_comma() {
        let (start, end) =
            retrieve_range_bounds("2020-01-01,2020-01-02").unwrap();
        assert!(end >= start);
    }

    #[test]
    fn retrieve_range_bounds_rejects_reverse() {
        assert!(retrieve_range_bounds("2020-01-02..2020-01-01").is_err());
    }

    #[test]
    fn unix_ts_rejects_pre_epoch() {
        let date =
            Date::from_calendar_date(1969, Month::December, 31).unwrap();
        let dt = date.midnight().assume_utc();
        assert!(unix_ts(&dt).is_err());
    }

    #[test]
    fn filter_quotes_by_range_is_inclusive() {
        let quotes = vec![
            make_quote(5),
            make_quote(10),
            make_quote(15),
            make_quote(21),
        ];
        let filtered = filter_quotes_by_range(quotes, 10, 20);
        let timestamps: Vec<u64> =
            filtered.into_iter().map(|q| q.timestamp).collect();
        assert_eq!(timestamps, vec![10, 15]);
    }
}
