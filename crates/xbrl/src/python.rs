use pyo3::prelude::*;

use crate::models::XbrlFact;
use crate::parser;

#[pyclass(name = "XbrlFact", frozen, module = "xbrl")]
#[derive(Debug, Clone)]
pub struct PyXbrlFact {
    #[pyo3(get)]
    pub tag: String,
    #[pyo3(get)]
    pub namespace: String,
    #[pyo3(get)]
    pub local_name: String,
    #[pyo3(get)]
    pub value: f64,
    #[pyo3(get)]
    pub raw_value: String,
    #[pyo3(get)]
    pub scale: i32,
    #[pyo3(get)]
    pub decimals: Option<i32>,
    #[pyo3(get)]
    pub unit: Option<String>,
    #[pyo3(get)]
    pub context_ref: String,
    #[pyo3(get)]
    pub period_start: Option<String>,
    #[pyo3(get)]
    pub period_end: Option<String>,
    #[pyo3(get)]
    pub period_instant: Option<String>,
    #[pyo3(get)]
    pub entity_id: Option<String>,
    #[pyo3(get)]
    pub segment: Option<String>,
}

impl From<XbrlFact> for PyXbrlFact {
    fn from(value: XbrlFact) -> Self {
        Self {
            tag: value.tag,
            namespace: value.namespace,
            local_name: value.local_name,
            value: value.value,
            raw_value: value.raw_value,
            scale: value.scale,
            decimals: value.decimals,
            unit: value.unit,
            context_ref: value.context_ref,
            period_start: value.period_start,
            period_end: value.period_end,
            period_instant: value.period_instant,
            entity_id: value.entity_id,
            segment: value.segment,
        }
    }
}

#[pymethods]
impl PyXbrlFact {
    fn __repr__(&self) -> String {
        format!(
            "XbrlFact(tag={}, context_ref={}, value={})",
            self.tag, self.context_ref, self.value
        )
    }
}

fn map_facts(result: Result<Vec<XbrlFact>, crate::error::XbrlError>) -> PyResult<Vec<PyXbrlFact>> {
    result
        .map(|facts| facts.into_iter().map(Into::into).collect())
        .map_err(|err| err.to_py_err())
}

#[pyclass(name = "PyXbrlParser", module = "xbrl")]
#[derive(Default)]
pub struct PyXbrlParser;

#[pymethods]
impl PyXbrlParser {
    #[new]
    fn new() -> Self {
        Self
    }

    fn parse_ixbrl(&self, content: &str) -> PyResult<Vec<PyXbrlFact>> {
        map_facts(parser::parse_ixbrl(content))
    }

    fn parse_instance(&self, content: &str) -> PyResult<Vec<PyXbrlFact>> {
        map_facts(parser::parse_instance(content))
    }

    fn parse_auto(&self, content: &str) -> PyResult<Vec<PyXbrlFact>> {
        map_facts(parser::parse_auto(content))
    }

    fn parse_file(&self, path: &str) -> PyResult<Vec<PyXbrlFact>> {
        map_facts(parser::parse_file(path))
    }
}

#[pyfunction]
pub fn extract_facts(content: &str) -> PyResult<Vec<PyXbrlFact>> {
    map_facts(parser::parse_auto(content))
}

#[pyfunction]
pub fn extract_facts_from_file(path: &str) -> PyResult<Vec<PyXbrlFact>> {
    map_facts(parser::parse_file(path))
}
