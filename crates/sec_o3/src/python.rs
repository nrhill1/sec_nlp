//! This module details the PyO3 bindings,
//! after which this crate is aptly named.
//!
//!
//!
//!
#![cfg(feature = "python")]

use pyo3::exceptions::{PyException, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use std::sync::OnceLock;
use tokio::runtime::Runtime;

use crate::{
    client::Client,
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

/// Python wrapper for Client
#[pyclass(name = "Client")]
struct PyClient {
    inner: Client,
}

#[pymethods]
impl PyClient {
    todo!();
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
fn sec_o3(py: Python<'_>, m: &PyModule) -> PyResult<()> {
    // Classes
    m.add_class::<PyClient>()?;
    m.add_class::<PyDocument>()?;

    // Module metadata
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("__author__", "nrhill1@gmail.com")?;

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
