//! Offline EFTS response parsing and keyword ranking for the Python HTTPX client.
//!
//! All SEC network requests are owned by sec_nlp.core.edgar.transport.

mod models;
mod parse;
mod ranking;
pub mod test_support;

use crate::models::{BatchSearchResult, ProgressInfo, SearchHit, SearchResponse};
use crate::ranking::{
    rank_documents_by_keywords, score_document_keywords, DocumentScore, KeywordResult,
    RakeExtractor, TextRankExtractor, TfIdfRanker, YakeExtractor,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// Parse downloaded EFTS JSON without making network requests.
#[pyfunction]
fn parse_response_json(content: &str, query: &str) -> PyResult<String> {
    let value: serde_json::Value =
        serde_json::from_str(content).map_err(|error| PyValueError::new_err(error.to_string()))?;
    if !value
        .get("hits")
        .and_then(|hits| hits.get("hits"))
        .is_some_and(|hits| hits.is_array())
    {
        return Err(PyValueError::new_err("EFTS response is missing hits.hits"));
    }
    serde_json::to_string(&parse::parse_response(&value, query))
        .map_err(|error| PyValueError::new_err(error.to_string()))
}

#[pymodule]
fn efts(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<SearchHit>()?;
    m.add_class::<SearchResponse>()?;
    m.add_class::<BatchSearchResult>()?;
    m.add_class::<ProgressInfo>()?;
    m.add_class::<YakeExtractor>()?;
    m.add_class::<RakeExtractor>()?;
    m.add_class::<TextRankExtractor>()?;
    m.add_class::<TfIdfRanker>()?;
    m.add_class::<KeywordResult>()?;
    m.add_class::<DocumentScore>()?;
    m.add_function(wrap_pyfunction!(parse_response_json, m)?)?;
    m.add_function(wrap_pyfunction!(score_document_keywords, m)?)?;
    m.add_function(wrap_pyfunction!(rank_documents_by_keywords, m)?)?;
    Ok(())
}
