//! Async HTTP utilities for EFTS requests.

use once_cell::sync::Lazy;
use reqwest::Client;
use serde_json::Value;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use crate::constants::DEFAULT_TIMEOUT_SECS;
use crate::error::EftsError;

static LAST_REQUEST_ASYNC: Lazy<Mutex<Instant>> =
    Lazy::new(|| Mutex::new(Instant::now() - Duration::from_secs(60)));

/// Build an async reqwest client with the given timeout.
pub(crate) fn build_async_client(timeout_seconds: f64) -> Result<Client, EftsError> {
    let timeout = if timeout_seconds > 0.0 {
        timeout_seconds
    } else {
        DEFAULT_TIMEOUT_SECS
    };
    Client::builder()
        .timeout(Duration::from_secs_f64(timeout))
        .build()
        .map_err(|err| {
            EftsError::new(
                0,
                format!("Failed to build async HTTP client: {}", err),
                None,
                false,
            )
        })
}

/// Async rate limiting - sleeps if needed to respect rate limits.
pub(crate) async fn enforce_rate_limit_async(rate_limit_delay_seconds: f64) {
    if rate_limit_delay_seconds <= 0.0 {
        return;
    }
    let delay = Duration::from_secs_f64(rate_limit_delay_seconds);
    let sleep_duration = {
        let mut last_request = LAST_REQUEST_ASYNC
            .lock()
            .expect("rate limit mutex should be available");
        let elapsed = last_request.elapsed();
        if elapsed < delay {
            Some(delay - elapsed)
        } else {
            *last_request = Instant::now();
            None
        }
    };
    if let Some(duration) = sleep_duration {
        tokio::time::sleep(duration).await;
        let mut last_request = LAST_REQUEST_ASYNC
            .lock()
            .expect("rate limit mutex should be available");
        *last_request = Instant::now();
    }
}

/// Make an async HTTP request to the EFTS API.
pub(crate) async fn make_request_async(
    client: &Client,
    base_url: &str,
    params: &[(String, String)],
    user_agent: &str,
) -> Result<Value, EftsError> {
    let response = client
        .get(base_url)
        .header("User-Agent", user_agent)
        .header("Accept", "application/json")
        .query(params)
        .send()
        .await
        .map_err(|err| {
            let retryable = err.is_timeout() || err.is_connect();
            EftsError::new(
                0,
                format!("Network error: {}", err),
                None,
                retryable,
            )
        })?;

    let status = response.status();
    let body = response.text().await.unwrap_or_default();
    if !status.is_success() {
        let retryable = status.as_u16() == 429 || status.as_u16() >= 500;
        let message = format!(
            "HTTP {}: {}",
            status.as_u16(),
            status.canonical_reason().unwrap_or("error")
        );
        let detail = if body.is_empty() { None } else { Some(body) };
        return Err(EftsError::new(status.as_u16(), message, detail, retryable));
    }

    serde_json::from_str(&body).map_err(|err| {
        EftsError::new(
            0,
            format!("JSON parse error: {}", err),
            Some(body),
            false,
        )
    })
}
