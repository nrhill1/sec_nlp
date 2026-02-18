mod context;
mod error;
mod facts;
mod linkbase;
mod models;
mod parser;
mod python;
mod taxonomy;

use pyo3::prelude::*;

use crate::python::{extract_facts, extract_facts_from_file, PyXbrlFact, PyXbrlParser};

#[pymodule]
fn xbrl(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyXbrlFact>()?;
    m.add_class::<PyXbrlParser>()?;
    m.add_function(wrap_pyfunction!(extract_facts, m)?)?;
    m.add_function(wrap_pyfunction!(extract_facts_from_file, m)?)?;
    Ok(())
}
