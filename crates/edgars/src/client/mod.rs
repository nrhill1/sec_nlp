//! HTTP client for SEC API requests.
//!
//! This module provides a Hyper-based HTTP client with built-in support
//! for rate limiting, retries, and request validation per SEC guidelines.
//!
//! # Submodules
//!
//! * [`rate_limit`] - Rate limiting to comply with SEC API limits
//! * [`retry`] - Retry logic with exponential backoff
//! * [`validation`] - Request and response validation
//!
//! # SEC API Requirements
//!
//! The SEC requires all automated requests to:
//! - Include a User-Agent header with contact information
//! - Respect rate limits (10 requests per second maximum)
//! - Handle 429 responses appropriately
//!
//! # Examples
//!
//! ```no_run
//! use edgars::client::SecClient;
//!
//! #[tokio::main]
//! async fn main() -> Result<(), Box<dyn std::error::Error>> {
//!     let client = SecClient::new("MyApp", "contact@example.com");
//!     
//!     let response = client.get("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json").await?;
//!     println!("Got response!");
//!     
//!     Ok(())
//! }
//! ```
//!

pub mod rate_limit;
pub mod retry;
pub mod validation;

use hyper::client::HttpConnector;
use hyper::{Body, Method, Request, Response, StatusCode, Uri};
use hyper_tls::HttpsConnector;
use std::time::Duration;

use crate::errors::{Error, Result};

use rate_limit::RateLimiter;
use retry::RetryPolicy;

/// SEC API client with rate limiting and retry support.
pub struct SecClient {
    client: hyper::Client<HttpsConnector<HttpConnector>>,
    rate_limiter: RateLimiter,
    retry_policy: RetryPolicy,
    user_agent: String,
}

impl SecClient {
    /// Create a new SEC client with default settings.
    ///
    /// # Arguments
    ///
    /// * `app_name` - Your application name
    /// * `contact` - Your contact email
    ///
    /// # Examples
    ///
    /// ```
    /// use edgars::client::SecClient;
    ///
    /// let client = SecClient::new("MyApp", "contact@example.com");
    /// ```
    pub fn new(app_name: &str, contact: &str) -> Self {
        let https = HttpsConnector::new();
        let client = hyper::Client::builder()
            .pool_idle_timeout(Duration::from_secs(30))
            .build::<_, Body>(https);

        Self {
            client,
            rate_limiter: RateLimiter::new(10, Duration::from_secs(1)), // 10 req/sec
            retry_policy: RetryPolicy::default(),
            user_agent: format!("{} {}", app_name, contact),
        }
    }

    /// Make a GET request to the specified URL.
    ///
    /// Automatically handles rate limiting, retries, and SEC-required headers.
    ///
    /// # Arguments
    ///
    /// * `url` - The URL to request
    ///
    /// # Returns
    ///
    /// The HTTP response on success.
    ///
    /// # Errors
    ///
    /// Returns an error if:
    /// - The URL is invalid
    /// - The request fails after retries
    /// - The response status is not successful
    pub async fn get(&self, url: &str) -> Result<Response<Body>> {
        let uri: Uri = url
            .parse()
            .map_err(|_| Error::Custom(format!("Invalid URL: {}", url)))?;

        self.request(Method::GET, uri).await
    }

    /// Make a request with the specified method and URI.
    async fn request(&self, method: Method, uri: Uri) -> Result<Response<Body>> {

        self.rate_limiter.wait().await;

        self.retry_policy
            .execute(|| {
                let uri = uri.clone();
                let client = self.client.clone();
                let user_agent = self.user_agent.clone();
                let method = method.clone();

                Box::pin(async move {
                    // Build request
                    let req = Request::builder()
                        .method(method)
                        .uri(uri.clone())
                        .header("User-Agent", &user_agent)
                        .header("Accept", "application/json")
                        .header("Accept-Encoding", "gzip, deflate")
                        .header("Host", "data.sec.gov")
                        .body(Body::empty())
                        .map_err(Error::HttpError)?;

                    let response = client.request(req).await.map_err(Error::HyperError)?;

                    // Check status
                    match response.status() {
                        StatusCode::OK => Ok(response),
                        StatusCode::TOO_MANY_REQUESTS => {
                            Err(Error::RateLimitExceeded("SEC rate limit exceeded".to_string()))
                        }
                        StatusCode::NOT_FOUND => Err(Error::NotFound(format!("Resource not found: {}", uri))),
                        status => Err(Error::InvalidStatus(status)),
                    }
                })
            })
            .await
    }

    /// Fetch JSON data from a URL and deserialize it.
    ///
    /// # Type Parameters
    ///
    /// * `T` - The type to deserialize into (must implement `serde::Deserialize`)
    ///
    /// # Arguments
    ///
    /// * `url` - The URL to fetch
    ///
    /// # Returns
    ///
    /// The deserialized data on success.
    pub async fn get_json<T>(&self, url: &str) -> Result<T>
    where
        T: serde::de::DeserializeOwned,
    {
        let response = self.get(url).await?;
        let body = hyper::body::to_bytes(response.into_body())
            .await
            .map_err(Error::HyperError)?;

        serde_json::from_slice(&body).map_err(Error::JsonError)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_client_creation() {
        let client = SecClient::new("TestApp", "test@example.com");
        assert!(client.user_agent.contains("TestApp"));
        assert!(client.user_agent.contains("test@example.com"));
    }
}


pub use crate::client;
