//! Python extension module for SEC EDGAR Full-Text Search (EFTS).

mod client;
mod constants;
mod error;
mod http;
mod models;
mod parse;
mod python;
pub mod test_support;
mod validate;

use pyo3::prelude::*;

use crate::client::EftsClient;
use crate::constants::{
    DEFAULT_MAX_RETRIES, DEFAULT_RATE_LIMIT_SECS, DEFAULT_RETRY_DELAY_SECS,
    DEFAULT_TIMEOUT_SECS, EFTS_BASE_URL,
};
use crate::error::EftsError;
use crate::python::create_efts_client;
use crate::validate::validate_base_url;

#[pymodule]
fn efts(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<EftsClient>()?;
    m.add_function(wrap_pyfunction!(create_efts_client, m)?)?;
    Ok(())
}

pub fn search_raw(
    query: &str,
    user_agent: &str,
    limit: u32,
) -> Result<serde_json::Value, EftsError> {
    if query.trim().is_empty() {
        return Err(EftsError::new(
            0,
            "query must be non-empty",
            None,
            false,
        ));
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
    validate_base_url(base_url)?;
    let client = EftsClient::new_internal(
        Some(user_agent.to_string()),
        DEFAULT_TIMEOUT_SECS,
        DEFAULT_MAX_RETRIES,
        DEFAULT_RETRY_DELAY_SECS,
        DEFAULT_RATE_LIMIT_SECS,
        Some(base_url.to_string()),
    )?;
    let response = client.execute_search(
        query,
        &[],
        &[],
        &[],
        None,
        None,
        limit,
        0,
        "score",
        "desc",
    )?;
    serde_json::to_value(response).map_err(|err| {
        EftsError::new(
            0,
            format!("Failed to serialize response: {}", err),
            None,
            false,
        )
    })
}
