// src/python.rs
#[cfg(feature = "python")]
use once_cell::sync::OnceCell;

#[cfg(feature = "python")]
use pyo3::prelude::*;

#[cfg(feature = "python")]
use crate::{
    fetch::SecClient,
    parse::{parse, DataFormat},
};

#[cfg(feature = "python")]
static RUNTIME: OnceCell<tokio::runtime::Runtime> = OnceCell::new();

#[cfg(feature = "python")]
fn rt() -> &'static tokio::runtime::Runtime {
    RUNTIME.get_or_init(|| {
        tokio::runtime::Builder::new_multi_thread()
            .worker_threads(2)
            .enable_time()
            .enable_io()
            .build()
            .expect("tokio runtime")
    })
}

#[cfg(feature = "python")]
#[pymodule]
#[pyo3(name = "edga_rs")]
fn edga_rs_py(_py: Python<'_>, m: &PyModule) -> PyResult<()> {
    #[pyclass]
    struct Fetch {
        inner: SecClient,
    }

    #[pymethods]
    impl Fetch {
        fn fetch_text<'py>(&self, py: Python<'py>, url: &str) -> PyResult<&'py PyAny> {
            let inner = self.inner.clone();
            let url = url.to_string();

            pyo3_asyncio::tokio::future_into_py(py, async move {
                inner
                    .fetch_text(&url)
                    .await
                    .map_err(|e| PyRuntimeError::new_err(e.to_string()))
            })
        }
    }

    #[pyfunction]
    fn parse_html(input: &str) -> PyResult<(String, Option<String>, usize)> {
        let out = parse(DataFormat::Html, input).map_err(map_err)?;
        Ok((out.form_type.to_string(), out.title, out.bytes))
    }

    #[pyfunction]
    fn parse_json(input: &str) -> PyResult<(String, Option<String>, usize)> {
        let out = parse(DataFormat::Json, input).map_err(map_err)?;
        Ok((out.form_type.to_string(), out.title, out.bytes))
    }

    m.add_class::<Fetch>()?;
    m.add_function(wrap_pyfunction!(parse_html, m)?)?;
    m.add_function(wrap_pyfunction!(parse_json, m)?)?;
    Ok(())
}

#[cfg(feature = "python")]
fn map_err<E: std::fmt::Display>(e: E) -> pyo3::PyErr {
    pyo3::exceptions::PyRuntimeError::new_err(e.to_string())
}
