use pyo3::prelude::*;

use crate::client::EftsClient;
use crate::constants::{DEFAULT_MAX_RETRIES, DEFAULT_RATE_LIMIT_SECS, DEFAULT_RETRY_DELAY_SECS};

#[pyfunction]
#[pyo3(signature = (email, company_name="SEC NLP Tool".to_string(), timeout=30.0))]
pub fn create_efts_client(
    email: String,
    company_name: String,
    timeout: f64,
) -> PyResult<EftsClient> {
    let user_agent = format!("{} ({})", company_name, email);
    EftsClient::new(
        Some(user_agent),
        timeout,
        DEFAULT_MAX_RETRIES,
        DEFAULT_RETRY_DELAY_SECS,
        DEFAULT_RATE_LIMIT_SECS,
        None,
    )
}
