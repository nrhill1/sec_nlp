//! Python extension module for SEC EDGAR Full-Text Search (EFTS).
//!
//! This module provides:
//! - EFTS client for searching SEC EDGAR filings
//! - Keyword extraction algorithms (YAKE, RAKE, TextRank, TF-IDF)
//! - Document ranking utilities

mod client;
mod constants;
mod error;
mod http;
mod http_async;
mod models;
mod parse;
mod python;
mod ranking;
pub mod test_support;
mod validate;

use pyo3::prelude::*;

use crate::client::EftsClient;
use crate::constants::{
    DEFAULT_MAX_RETRIES, DEFAULT_RATE_LIMIT_SECS, DEFAULT_RETRY_DELAY_SECS, DEFAULT_TIMEOUT_SECS,
    EFTS_BASE_URL,
};
use crate::error::{EftsApiError, EftsError};
use crate::models::{BatchSearchResult, ProgressInfo, SearchHit, SearchResponse};
use crate::python::create_efts_client;
use crate::ranking::{
    rank_documents_by_keywords, score_document_keywords, DocumentScore, KeywordResult,
    RakeExtractor, TextRankExtractor, TfIdfRanker, YakeExtractor,
};

#[pymodule]
fn efts(py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Client class
    m.add_class::<EftsClient>()?;

    // Response model classes
    m.add_class::<SearchHit>()?;
    m.add_class::<SearchResponse>()?;
    m.add_class::<BatchSearchResult>()?;
    m.add_class::<ProgressInfo>()?;

    // Keyword extraction classes
    m.add_class::<YakeExtractor>()?;
    m.add_class::<RakeExtractor>()?;
    m.add_class::<TextRankExtractor>()?;
    m.add_class::<TfIdfRanker>()?;
    m.add_class::<KeywordResult>()?;
    m.add_class::<DocumentScore>()?;

    // Exception class
    m.add("EFTSAPIError", py.get_type::<EftsApiError>())?;

    // Factory functions
    m.add_function(wrap_pyfunction!(create_efts_client, m)?)?;
    m.add_function(wrap_pyfunction!(score_document_keywords, m)?)?;
    m.add_function(wrap_pyfunction!(rank_documents_by_keywords, m)?)?;
    Ok(())
}

pub fn search_raw(
    query: &str,
    user_agent: &str,
    limit: u32,
) -> Result<serde_json::Value, EftsError> {
    if query.trim().is_empty() {
        return Err(EftsError::new(0, "query must be non-empty", None, false));
    }
    let user_agent = user_agent.trim();
    if user_agent.is_empty() {
        return Err(EftsError::new(
            0,
            "user_agent must be non-empty",
            None,
            false,
        ));
    }
    let base_url = EFTS_BASE_URL;
    let client = EftsClient::new_internal(
        Some(user_agent.to_string()),
        DEFAULT_TIMEOUT_SECS,
        DEFAULT_MAX_RETRIES,
        DEFAULT_RETRY_DELAY_SECS,
        DEFAULT_RATE_LIMIT_SECS,
        Some(base_url.to_string()),
    )?;
    let response =
        client.execute_search(query, &[], &[], &[], None, None, limit, 0, "score", "desc")?;
    serde_json::to_value(response).map_err(|err| {
        EftsError::new(
            0,
            format!("Failed to serialize response: {}", err),
            None,
            false,
        )
    })
}
