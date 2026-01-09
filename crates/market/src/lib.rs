use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::future::Future;
use yahoo_finance_api::YahooConnector;

const QUOTE_RANGE: &str = "1d";

fn to_py_err<E: std::fmt::Display>(err: E) -> PyErr {
    PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(err.to_string())
}

fn run_async<T>(future: impl Future<Output = PyResult<T>>) -> PyResult<T> {
    let runtime = tokio::runtime::Runtime::new().map_err(to_py_err)?;
    runtime.block_on(future)
}

async fn fetch_price_async(ticker: String) -> PyResult<f64> {
    let provider = YahooConnector::new();
    let response = provider
        .get_latest_quotes(&ticker, QUOTE_RANGE)
        .await
        .map_err(to_py_err)?;
    let quote = response.last_quote().map_err(to_py_err)?;
    Ok(quote.close)
}

async fn fetch_prices_async(tickers: Vec<String>) -> PyResult<Vec<(String, f64)>> {
    let provider = YahooConnector::new();
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

#[pymodule]
fn market(_py: Python<'_>, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(fetch_price, m)?)?;
    m.add_function(wrap_pyfunction!(fetch_prices, m)?)?;
    Ok(())
}
