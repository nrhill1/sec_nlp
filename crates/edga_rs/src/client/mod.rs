// src/client/mod.rs - HTTP client with rate limiting and retry logic
pub mod rate_limit;
pub mod retry;
pub mod validation;

use std::time::Duration;

use http_body_util::BodyExt;
use hyper::Request;
use hyper_tls::HttpsConnector;
use hyper_util::client::legacy::{connect::HttpConnector, Client};
use hyper_util::rt::TokioExecutor;
use tokio::time::timeout;

use crate::errors::{FetchError, NetworkError, ParseError};
use rate_limit::SecRateLimiter;
use retry::RetryPolicy;
use validation::validate_sec_url;

/// Module-specific Result type for fetch operations
pub type Result<T> = std::result::Result<T, FetchError>;

pub const DEFAULT_UA: &str = "edga_rs/0.1 (+https://www.sec.gov/; contact=example@example.com)";

/// HTTP client using modern hyper v1 (HTTP/1 & HTTP/2 via ALPN).
///
/// Includes rate limiting and retry logic for SEC API compliance.
pub struct SecClient {
    client: Client<HttpsConnector<HttpConnector>, String>,
    timeout: Duration,
    user_agent: String,
    rate_limiter: Option<SecRateLimiter>,
    retry_policy: Option<RetryPolicy>,
}

impl Default for SecClient {
    fn default() -> Self {
        let https = HttpsConnector::new();
        let client = Client::builder(TokioExecutor::new()).build::<_, String>(https);
        Self {
            client,
            timeout: Duration::from_secs(30),
            user_agent: DEFAULT_UA.to_string(),
            rate_limiter: Some(SecRateLimiter::new()),
            retry_policy: Some(RetryPolicy::default()),
        }
    }
}

impl SecClient {
    /// Create a new SEC client with default settings.
    pub fn new() -> Self {
        Self::default()
    }

    /// Create a new SEC client with custom user agent.
    /// The SEC requires a valid contact email in the User-Agent.
    pub fn with_user_agent(user_agent: impl Into<String>) -> Self {
        Self {
            user_agent: user_agent.into(),
            ..Default::default()
        }
    }

    /// Create a new SEC client with custom timeout.
    pub fn with_timeout(timeout: Duration) -> Self {
        Self {
            timeout,
            ..Default::default()
        }
    }

    /// Builder pattern: set custom user agent
    pub fn user_agent(mut self, ua: impl Into<String>) -> Self {
        self.user_agent = ua.into();
        self
    }

    /// Builder pattern: set timeout
    pub fn timeout(mut self, timeout: Duration) -> Self {
        self.timeout = timeout;
        self
    }

    /// Builder pattern: disable rate limiting
    pub fn without_rate_limit(mut self) -> Self {
        self.rate_limiter = None;
        self
    }

    /// Builder pattern: disable retry logic
    pub fn without_retry(mut self) -> Self {
        self.retry_policy = None;
        self
    }

    /// Fetch text content with timeout and proper User-Agent.
    pub async fn fetch_text(&self, url: &str) -> Result<String> {
        validate_sec_url(url)?;

        if let Some(limiter) = &self.rate_limiter {
            limiter.wait().await;
        }

        let req = Request::builder()
            .method("GET")
            .uri(url)
            .header("User-Agent", &self.user_agent)
            .header("Accept", "text/plain")
            .body(String::new())
            .map_err(|e| FetchError::Network(NetworkError::General(e.to_string())))?;

        let res = timeout(self.timeout, self.client.request(req))
            .await
            .map_err(|e| FetchError::Network(e.into()))?
            .map_err(|e| FetchError::Network(NetworkError::General(e.to_string())))?;

        let status = res.status();
        if !status.is_success() {
            return Err(FetchError::Network(NetworkError::from_status(status.as_u16())));
        }

        let body = res.into_body();
        let bytes = body
            .collect()
            .await
            .map_err(|e| FetchError::Network(NetworkError::General(e.to_string())))?
            .to_bytes();

        String::from_utf8(bytes.to_vec()).map_err(|e| FetchError::Parse(ParseError::Utf8(e)))
    }

    /// Fetch raw bytes (binary content).
    pub async fn fetch_bytes(&self, url: &str) -> Result<Vec<u8>> {
        validate_sec_url(url)?;

        if let Some(limiter) = &self.rate_limiter {
            limiter.wait().await;
        }

        let req = Request::builder()
            .method("GET")
            .uri(url)
            .header("User-Agent", &self.user_agent)
            .header("Accept", "*/*")
            .body(String::new())
            .map_err(|e| FetchError::Network(NetworkError::General(e.to_string())))?;

        let res = timeout(self.timeout, self.client.request(req))
            .await
            .map_err(|e| FetchError::Network(e.into()))?
            .map_err(|e| FetchError::Network(NetworkError::General(e.to_string())))?;

        let status = res.status();
        if !status.is_success() {
            return Err(FetchError::Network(NetworkError::from_status(status.as_u16())));
        }

        let body = res.into_body();
        let bytes = body
            .collect()
            .await
            .map_err(|e| FetchError::Network(NetworkError::General(e.to_string())))?
            .to_bytes();

        Ok(bytes.to_vec())
    }

    /// Fetch and parse JSON in one operation.
    pub async fn fetch_and_parse_json<T: for<'de> serde::Deserialize<'de>>(&self, url: &str) -> Result<T> {
        let text = self.fetch_text(url).await?;
        let value = serde_json::from_str::<T>(&text).map_err(|e| FetchError::Parse(ParseError::Json(e)))?;
        Ok(value)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_client_creation() {
        let client = SecClient::new();
        assert_eq!(client.timeout, Duration::from_secs(30));
    }

    #[test]
    fn test_client_builder() {
        let client = SecClient::new()
            .user_agent("custom/1.0")
            .timeout(Duration::from_secs(60))
            .without_rate_limit();

        assert_eq!(client.timeout, Duration::from_secs(60));
        assert_eq!(client.user_agent, "custom/1.0");
        assert!(client.rate_limiter.is_none());
    }
}
