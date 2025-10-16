//! HTTP client module for SEC/EDGAR API interactions.
//!
//! This module provides an async HTTP client with built-in rate limiting,
//! retry logic, and SEC-specific request validation.

mod rate_limit;
mod retry;

use std::sync::Arc;
use std::time::Duration;

use http_body_util::BodyExt;
use hyper::Request;
use hyper_tls::HttpsConnector;
use hyper_util::client::legacy::{connect::HttpConnector, Client};
use hyper_util::rt::TokioExecutor;
use tokio::time::timeout;

use crate::errors::{EdgarError, Result};
use rate_limit::SecRateLimiter;
use retry::RetryPolicy;

pub use rate_limit::SecRateLimiter as RateLimiter;

pub const DEFAULT_UA: &str = "edgars/0.1 (+https://github.com/yourusername/edgars; contact@example.com)";
pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(30);

/// An async HTTP client for SEC/EDGAR API interactions.
///
/// This client provides:
/// - Automatic rate limiting (default: 10 requests/second per SEC requirements)
/// - Retry logic with exponential backoff for transient failures
/// - HTTPS-only enforcement for SEC domains
/// - Configurable timeout and user agent
///
/// # Examples
///
/// ```rust,no_run
/// use edgars::SecClient;
///
/// #[tokio::main]
/// async fn main() -> Result<(), Box<dyn std::error::Error>> {
///     let client = SecClient::new()
///         .with_user_agent("MyApp/1.0 (contact@example.com)")
///         .with_timeout(std::time::Duration::from_secs(60));
///
///     let text = client.fetch_text("https://www.sec.gov/files/company_tickers.json").await?;
///     Ok(())
/// }
/// ```
#[derive(Clone)]
pub struct SecClient {
    client: Arc<Client<HttpsConnector<HttpConnector>, String>>,
    timeout: Duration,
    user_agent: String,
    rate_limiter: Arc<SecRateLimiter>,
    retry_policy: Option<RetryPolicy>,
}

impl Default for SecClient {
    fn default() -> Self {
        Self::new()
    }
}

impl SecClient {
    /// Create a new SEC client with sensible defaults.
    ///
    /// Default configuration:
    /// - User agent: "edgars/0.1"
    /// - Timeout: 30 seconds
    /// - Rate limit: 10 requests/second (SEC requirement)
    /// - Retry policy: 3 attempts with exponential backoff
    pub fn new() -> Self {
        let https = HttpsConnector::new();
        let client = Client::builder(TokioExecutor::new()).build::<_, String>(https);

        Self {
            client: Arc::new(client),
            timeout: DEFAULT_TIMEOUT,
            user_agent: DEFAULT_UA.to_string(),
            rate_limiter: Arc::new(SecRateLimiter::new()),
            retry_policy: Some(RetryPolicy::default()),
        }
    }

    // Return a reference to the inner client
    pub fn client(&self) -> &Client<HttpsConnector<HttpConnector>, String> {
        &self.client
    }

    /// Returns the configured User-Agent string.
    pub fn user_agent(&self) -> &str {
        &self.user_agent
    }

    /// Provides access to the rate limiter (useful for custom request batching).
    pub fn rate_limiter(&self) -> &SecRateLimiter {
        &self.rate_limiter
    }

    /// Set a custom user agent string.
    ///
    /// The SEC requires a valid user agent with contact information.
    ///
    /// # Arguments
    ///
    /// * `ua` - User agent string (e.g., "MyApp/1.0 (contact@example.com)")
    pub fn with_user_agent(mut self, ua: impl Into<String>) -> Self {
        self.user_agent = ua.into();
        self
    }

    /// Set a custom timeout duration.
    ///
    /// # Arguments
    ///
    /// * `timeout` - Maximum duration to wait for a response
    pub fn with_timeout(mut self, timeout: Duration) -> Self {
        self.timeout = timeout;
        self
    }

    /// Disable rate limiting (not recommended for SEC API).
    ///
    /// The SEC requires rate limiting to 10 requests per second.
    /// Only disable this if you have explicit permission or are using a local cache.
    pub fn without_rate_limit(mut self) -> Self {
        self.rate_limiter = Arc::new(SecRateLimiter::unlimited());
        self
    }

    /// Disable retry logic.
    ///
    /// By default, the client retries failed requests with exponential backoff.
    /// Use this to disable retries entirely.
    pub fn without_retry(mut self) -> Self {
        self.retry_policy = None;
        self
    }

    /// Set a custom rate limit.
    ///
    /// # Arguments
    ///
    /// * `requests_per_second` - Maximum requests per second (SEC default is 10)
    pub fn with_rate_limit(mut self, requests_per_second: u32) -> Self {
        self.rate_limiter = Arc::new(SecRateLimiter::with_rate(requests_per_second));
        self
    }

    /// Fetch text content from a URL.
    ///
    /// # Arguments
    ///
    /// * `url` - The URL to fetch (must be HTTPS and on sec.gov domain)
    ///
    /// # Errors
    ///
    /// Returns an error if:
    /// - The URL is not HTTPS
    /// - The URL is not on the sec.gov domain
    /// - The request times out
    /// - The server returns an error status
    pub async fn fetch_text(&self, url: &str) -> Result<String> {
        self.validate_url(url)?;

        if let Some(policy) = &self.retry_policy {
            self.fetch_text_with_retry(url, policy).await
        } else {
            self.fetch_text_once(url).await
        }
    }

    /// Fetch and parse JSON from a URL.
    ///
    /// # Arguments
    ///
    /// * `url` - The URL to fetch (must be HTTPS and on sec.gov domain)
    ///
    /// # Type Parameters
    ///
    /// * `T` - The type to deserialize the JSON into
    ///
    /// # Errors
    ///
    /// Returns an error if the request fails or JSON parsing fails.
    pub async fn fetch_json<T: for<'de> serde::Deserialize<'de>>(&self, url: &str) -> Result<T> {
        let text = self.fetch_text(url).await?;
        serde_json::from_str(&text).map_err(|e| e.into())
    }

    /// Fetch raw bytes from a URL.
    ///
    /// # Arguments
    ///
    /// * `url` - The URL to fetch (must be HTTPS and on sec.gov domain)
    ///
    /// # Errors
    ///
    /// Returns an error if the request fails.
    pub async fn fetch_bytes(&self, url: &str) -> Result<Vec<u8>> {
        self.validate_url(url)?;

        self.rate_limiter.wait().await;

        let req = self.build_request(url, "*/*")?;
        let res = self.execute_request(req).await?;

        let body = res.into_body();
        let bytes = body
            .collect()
            .await
            .map_err(|e| EdgarError::Network(e.to_string()))?
            .to_bytes();

        Ok(bytes.to_vec())
    }

    // Private methods
    async fn fetch_text_once(&self, url: &str) -> Result<String> {
        self.rate_limiter.wait().await;

        let req = self.build_request(url, "text/plain")?;
        let res = self.execute_request(req).await?;

        let body = res.into_body();
        let bytes = body
            .collect()
            .await
            .map_err(|e| EdgarError::Network(e.to_string()))?
            .to_bytes();

        String::from_utf8(bytes.to_vec()).map_err(|e| e.into())
    }

    async fn fetch_text_with_retry(&self, url: &str, policy: &RetryPolicy) -> Result<String> {
        let mut attempt = 0;
        let mut delay = policy.initial_delay;

        loop {
            attempt += 1;

            match self.fetch_text_once(url).await {
                Ok(result) => return Ok(result),
                Err(e) if e.is_retryable() && attempt < policy.max_attempts => {
                    tracing::debug!(
                        "Attempt {}/{} failed: {}. Retrying in {:?}",
                        attempt,
                        policy.max_attempts,
                        e,
                        delay
                    );
                    tokio::time::sleep(delay).await;
                    delay = std::cmp::min(
                        Duration::from_secs_f64(delay.as_secs_f64() * policy.multiplier),
                        policy.max_delay,
                    );
                }
                Err(e) => return Err(e),
            }
        }
    }

    fn build_request(&self, url: &str, accept: &str) -> Result<Request<String>> {
        Request::builder()
            .method("GET")
            .uri(url)
            .header("User-Agent", &self.user_agent)
            .header("Accept", accept)
            .header("Accept-Encoding", "gzip, deflate")
            .body(String::new())
            .map_err(|e| EdgarError::Network(e.to_string()))
    }

    async fn execute_request(&self, req: Request<String>) -> Result<hyper::Response<hyper::body::Incoming>> {
        let res = timeout(self.timeout, self.client.request(req))
            .await
            .map_err(|_| EdgarError::Timeout(self.timeout.as_secs()))?
            .map_err(|e| EdgarError::Network(e.to_string()))?;

        let status = res.status();
        if !status.is_success() {
            return Err(EdgarError::http_status(status.as_u16()));
        }

        Ok(res)
    }

    fn validate_url(&self, url: &str) -> Result<()> {
        let parsed = url::Url::parse(url)?;

        if parsed.scheme() != "https" {
            return Err(EdgarError::Validation(
                "Only HTTPS URLs allowed for SEC requests".into(),
            ));
        }

        if let Some(host) = parsed.host_str() {
            if !host.ends_with("sec.gov") {
                return Err(EdgarError::Validation(format!(
                    "Only sec.gov URLs allowed, got: {}",
                    host
                )));
            }
        } else {
            return Err(EdgarError::Validation("URL missing host".into()));
        }

        Ok(())
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
            .with_user_agent("custom/1.0")
            .with_timeout(Duration::from_secs(60));

        assert_eq!(client.timeout, Duration::from_secs(60));
        assert_eq!(client.user_agent, "custom/1.0");
    }

    #[test]
    fn test_url_validation() {
        let client = SecClient::new();

        // Valid URLs
        assert!(client.validate_url("https://www.sec.gov/cgi-bin/browse-edgar").is_ok());
        assert!(client
            .validate_url("https://data.sec.gov/submissions/CIK0000320193.json")
            .is_ok());

        // Invalid URLs
        assert!(client.validate_url("http://www.sec.gov/test").is_err());
        assert!(client.validate_url("https://example.com/test").is_err());
        assert!(client.validate_url("not a url").is_err());
    }

    #[tokio::test]
    async fn test_client_is_cloneable() {
        let client = SecClient::new();
        let client2 = client.clone();

        // Both should work independently
        assert_eq!(client.user_agent, client2.user_agent);
    }
}
