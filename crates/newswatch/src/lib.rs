pub mod client;
pub mod dedup;
pub mod error;
pub mod feeds;
pub mod filter;
pub mod http;
pub mod models;
mod python;

use pyo3::prelude::*;

#[pymodule]
fn newswatch(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<models::NewsItem>()?;
    m.add_class::<python::NewsClient>()?;
    Ok(())
}
