// src/python.rs - Optimized Python bindings via PyO3
#![cfg(feature = "python")]

use pyo3::exceptions::{PyException, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use std::sync::OnceLock;
use tokio::runtime::Runtime;

use crate::{
    client::SecClient,
    corp::{
        cik::{get_ticker_map, normalize_cik, ticker_to_cik},
        facts::fetch_company_facts,
        submissions::fetch_company_filings,
    },
    parse::{parse_auto, parse_html, parse_json, Format},
};

// Tokio runtime singleton
static RUNTIME: OnceLock<Runtime> = OnceLock::new();

fn runtime() -> &'static Runtime {
    RUNTIME.get_or_init(|| Runtime::new().expect("Failed to create Tokio runtime"))
}

/// Python wrapper for SecClient
#[pyclass(name = "Client")]
struct PyClient {
    inner: SecClient,
}

#[pymethods]
impl PyClient {
    #[new]
    #[pyo3(signature = (user_agent=None, timeout=None))]
    fn new(user_agent: Option<String>, timeout: Option<u64>) -> Self {
        let mut client = SecClient::new();

        if let Some(ua) = user_agent {
            client = client.with_user_agent(ua);
        }

        if let Some(t) = timeout {
            client = client.with_timeout(std::time::Duration::from_secs(t));
        }

        Self { inner: client }
    }

    /// Fetch text content from URL
    fn fetch_text(&self, url: &str) -> PyResult<String> {
        let client = self.inner.clone();
        let url = url.to_string();

        runtime()
            .block_on(async move { client.fetch_text(&url).await })
            .map_err(to_py_err)
    }

    /// Fetch and parse JSON
    fn fetch_json(&self, url: &str) -> PyResult<PyObject> {
        let text = self.fetch_text(url)?;
        Python::with_gil(|py| {
            let json_module = py.import("json")?;
            json_module.call_method1("loads", (text,))?.extract()
        })
    }

    /// Fetch raw bytes
    fn fetch_bytes(&self, url: &str) -> PyResult<Vec<u8>> {
        let client = self.inner.clone();
        let url = url.to_string();

        runtime()
            .block_on(async move { client.fetch_bytes(&url).await })
            .map_err(to_py_err)
    }
}

/// Python wrapper for parsed documents
#[pyclass(name = "Document")]
#[derive(Clone)]
struct PyDocument {
    #[pyo3(get)]
    form_type: String,
    #[pyo3(get)]
    format: String,
    #[pyo3(get)]
    title: Option<String>,
    #[pyo3(get)]
    size_bytes: usize,
}

/// Normalize CIK to 10-digit format
#[pyfunction]
fn normalize_cik_str(cik: &str) -> String {
    normalize_cik(cik)
}

/// Look up CIK by ticker symbol
#[pyfunction]
fn lookup_ticker(ticker: &str) -> PyResult<String> {
    runtime()
        .block_on(async move { ticker_to_cik(ticker).await })
        .map_err(to_py_err)
}

/// Get all ticker-to-CIK mappings
#[pyfunction]
fn get_all_tickers() -> PyResult<Vec<(String, String)>> {
    let map = runtime()
        .block_on(async move { get_ticker_map().await })
        .map_err(to_py_err)?;

    Ok(map.iter().map(|(k, v)| (k.clone(), v.clone())).collect())
}

/// Fetch company facts (XBRL data)
#[pyfunction]
fn get_company_facts(cik: &str) -> PyResult<PyObject> {
    let facts = runtime()
        .block_on(async move { fetch_company_facts(cik).await })
        .map_err(to_py_err)?;

    Python::with_gil(|py| {
        let json_str = serde_json::to_string(&facts).map_err(|e| PyException::new_err(e.to_string()))?;
        let json_module = py.import("json")?;
        json_module.call_method1("loads", (json_str,))?.extract()
    })
}

/// Fetch company filings/submissions
#[pyfunction]
fn get_company_filings(cik: &str) -> PyResult<PyObject> {
    let submissions = runtime()
        .block_on(async move { fetch_company_filings(cik).await })
        .map_err(to_py_err)?;

    Python::with_gil(|py| {
        let json_str = serde_json::to_string(&submissions).map_err(|e| PyException::new_err(e.to_string()))?;
        let json_module = py.import("json")?;
        json_module.call_method1("loads", (json_str,))?.extract()
    })
}

/// Parse HTML document
#[pyfunction]
fn parse_html_doc(html: &str) -> PyResult<PyDocument> {
    let doc = parse_html(html).map_err(to_py_err)?;
    Ok(PyDocument {
        form_type: doc.form_type.to_string(),
        format: doc.format.to_string(),
        title: doc.title,
        size_bytes: doc.size_bytes,
    })
}

/// Parse JSON document
#[pyfunction]
fn parse_json_doc(json: &str) -> PyResult<PyDocument> {
    let doc = parse_json(json).map_err(to_py_err)?;
    Ok(PyDocument {
        form_type: doc.form_type.to_string(),
        format: doc.format.to_string(),
        title: doc.title,
        size_bytes: doc.size_bytes,
    })
}

/// Auto-detect format and parse
#[pyfunction]
fn parse_document(content: &str) -> PyResult<PyDocument> {
    let doc = parse_auto(content).map_err(to_py_err)?;
    Ok(PyDocument {
        form_type: doc.form_type.to_string(),
        format: doc.format.to_string(),
        title: doc.title,
        size_bytes: doc.size_bytes,
    })
}

/// Convert Rust error to Python exception
fn to_py_err(err: crate::errors::EdgarError) -> PyErr {
    use crate::errors::EdgarError;

    match err {
        EdgarError::Validation(msg) => PyValueError::new_err(msg),
        EdgarError::NotFound(msg) => PyValueError::new_err(msg),
        _ => PyRuntimeError::new_err(err.to_string()),
    }
}

/// Python module definition
#[pymodule]
fn edgars(py: Python<'_>, m: &PyModule) -> PyResult<()> {
    // Classes
    m.add_class::<PyClient>()?;
    m.add_class::<PyDocument>()?;

    // Functions - CIK/Ticker
    m.add_function(wrap_pyfunction!(normalize_cik_str, m)?)?;
    m.add_function(wrap_pyfunction!(lookup_ticker, m)?)?;
    m.add_function(wrap_pyfunction!(get_all_tickers, m)?)?;

    // Functions - Data fetching
    m.add_function(wrap_pyfunction!(get_company_facts, m)?)?;
    m.add_function(wrap_pyfunction!(get_company_filings, m)?)?;

    // Functions - Parsing
    m.add_function(wrap_pyfunction!(parse_html_doc, m)?)?;
    m.add_function(wrap_pyfunction!(parse_json_doc, m)?)?;
    m.add_function(wrap_pyfunction!(parse_document, m)?)?;

    // Module metadata
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("__author__", "Nicolas Hill")?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_runtime_creation() {
        let rt = runtime();
        assert!(rt.handle().metrics().num_workers() > 0);
    }

    #[test]
    fn test_normalize_cik_binding() {
        assert_eq!(normalize_cik_str("320193"), "0000320193");
    }
}
