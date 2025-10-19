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
//! - Include a User-Agent header with contact_email information
//! - Respect rate limits (10 requests per second maximum)
//! - Handle 429 responses appropriately
//!
//! # Examples
//!
//! ```no_run
//! use sec_o3::client::Client;
//!
//! #[tokio::main]
//! async fn main() -> Result<(), Box<dyn std::error::Error>> {
//!     let client = Client::new("MyApp", "contact_email@example.com");
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
use async_compression::tokio::bufread::{GzipDecoder, ZlibDecoder};
use futures::TryStreamExt;
use hyper::client::HttpConnector;
use hyper::{Body, Method, Request, Response, StatusCode, Uri};
use hyper_tls::HttpsConnector;
use std::path::Path;
use std::sync::Arc;
use std::time::Duration;
use tokio::fs;
use tokio::io::{AsyncReadExt, BufReader};

use crate::errors::{Error, Result};
use rate_limit::RateLimiter;
use retry::RetryPolicy;

/// SEC API client with rate limiting, retry support, and async decompression.
#[derive(Clone)]
pub struct Client {
    inner: Arc<ClientInner>,
}

struct ClientInner {
    client: hyper::Client<HttpsConnector<HttpConnector>>,
    rate_limiter: RateLimiter,
    retry_policy: RetryPolicy,
    user_agent: String,
}

impl Client {
    /// Create a new SEC client with default settings.
    pub fn new(contact_name: &str, contact_email: &str) -> Self {
        let https = HttpsConnector::new();
        let client = hyper::Client::builder()
            .pool_idle_timeout(Duration::from_secs(30))
            .http2_keep_alive_interval(Some(Duration::from_secs(15)))
            .http2_keep_alive_timeout(Duration::from_secs(5))
            .build::<_, Body>(https);

        Self {
            inner: Arc::new(ClientInner {
                client,
                rate_limiter: RateLimiter::new(10, Duration::from_secs(1)),
                retry_policy: RetryPolicy::default(),
                user_agent: format!("{} {}", contact_name, contact_email),
            }),
        }
    }

    /// Create client from USER_AGENT environment variable.
    pub fn from_env() -> Result<Self> {
        let user_agent = std::env::var("USER_AGENT").map_err(|_| Error::Custom("USER_AGENT not set".into()))?;

        if !user_agent.contains('@') {
            return Err(Error::Custom(
                "USER_AGENT must include email per SEC requirements".into(),
            ));
        }

        let https = HttpsConnector::new();
        let client = hyper::Client::builder()
            .pool_idle_timeout(Duration::from_secs(30))
            .http2_keep_alive_interval(Some(Duration::from_secs(15)))
            .http2_keep_alive_timeout(Duration::from_secs(5))
            .build::<_, Body>(https);

        Ok(Self {
            inner: Arc::new(ClientInner {
                client,
                rate_limiter: RateLimiter::new(10, Duration::from_secs(1)),
                retry_policy: RetryPolicy::default(),
                user_agent,
            }),
        })
    }

    /// Make a GET request with automatic retries and rate limiting.
    pub async fn get(&self, url: &str) -> Result<Response<Body>> {
        let uri: Uri = url
            .parse()
            .map_err(|_| Error::Custom(format!("Invalid URL: {}", url)))?;
        self.request(Method::GET, uri).await
    }

    /// Get response body as decompressed bytes.
    /// Automatically handles gzip and deflate based on Content-Encoding header.
    pub async fn get_bytes(&self, url: &str) -> Result<bytes::Bytes> {
        let response = self.get(url).await?;
        self.decode_response(response).await
    }

    /// Get response body as UTF-8 string with automatic decompression.
    pub async fn get_text(&self, url: &str) -> Result<String> {
        let bytes = self.get_bytes(url).await?;
        String::from_utf8(bytes.to_vec()).map_err(|e| Error::Custom(format!("Invalid UTF-8: {}", e)))
    }

    /// Fetch and deserialize JSON with automatic decompression.
    pub async fn get_json<T>(&self, url: &str) -> Result<T>
    where
        T: serde::de::DeserializeOwned,
    {
        let bytes = self.get_bytes(url).await?;
        serde_json::from_slice(&bytes).map_err(Error::JsonError)
    }

    /// Download text file with UTF-8 validation and automatic decompression.
    pub async fn download_text(&self, url: &str, path: impl AsRef<Path>) -> Result<()> {
        let bytes = self.get_bytes(url).await?;

        let text = std::str::from_utf8(&bytes).map_err(|e| Error::Custom(format!("Invalid UTF-8: {}", e)))?;

        fs::write(path, text).await.map_err(Error::IoError)?;
        Ok(())
    }

    /// Download raw bytes with automatic decompression.
    pub async fn download_bytes(&self, url: &str, path: impl AsRef<Path>) -> Result<()> {
        let bytes = self.get_bytes(url).await?;
        fs::write(path, &bytes).await.map_err(Error::IoError)?;
        Ok(())
    }

    /// Stream large file directly to disk with async decompression.
    pub async fn download_streaming(&self, url: &str, path: impl AsRef<Path>) -> Result<()> {
        let response = self.get(url).await?;

        let encoding = response
            .headers()
            .get(hyper::header::CONTENT_ENCODING)
            .and_then(|v| v.to_str().ok())
            .map(|s| s.to_lowercase());

        let body = response.into_body();
        let mut reader =
            tokio_util::io::StreamReader::new(body.map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e)));

        let mut file = fs::File::create(path).await.map_err(Error::IoError)?;

        match encoding.as_deref() {
            Some("gzip") => {
                let mut decoder = GzipDecoder::new(BufReader::new(reader));
                tokio::io::copy(&mut decoder, &mut file)
                    .await
                    .map_err(|e| Error::Custom(format!("Gzip streaming failed: {}", e)))?;
            }
            Some("deflate") => {
                let mut decoder = ZlibDecoder::new(BufReader::new(reader));
                tokio::io::copy(&mut decoder, &mut file)
                    .await
                    .map_err(|e| Error::Custom(format!("Deflate streaming failed: {}", e)))?;
            }
            _ => {
                tokio::io::copy(&mut reader, &mut file).await.map_err(Error::IoError)?;
            }
        }

        Ok(())
    }

    /// Asynchronously decodes response body based on Content-Encoding header.
    async fn decode_response(&self, response: Response<Body>) -> Result<bytes::Bytes> {
        let encoding = response
            .headers()
            .get(hyper::header::CONTENT_ENCODING)
            .and_then(|v| v.to_str().ok())
            .map(|s| s.to_lowercase());

        let body = hyper::body::to_bytes(response.into_body())
            .await
            .map_err(Error::HyperError)?;

        match encoding.as_deref() {
            Some("gzip") => {
                let mut decoder = GzipDecoder::new(BufReader::new(&body[..]));
                let mut decoded = Vec::new();
                decoder
                    .read_to_end(&mut decoded)
                    .await
                    .map_err(|e| Error::Custom(format!("Gzip decompression failed: {}", e)))?;
                Ok(bytes::Bytes::from(decoded))
            }
            Some("deflate") => {
                let mut decoder = ZlibDecoder::new(BufReader::new(&body[..]));
                let mut decoded = Vec::new();
                decoder
                    .read_to_end(&mut decoded)
                    .await
                    .map_err(|e| Error::Custom(format!("Deflate decompression failed: {}", e)))?;
                Ok(bytes::Bytes::from(decoded))
            }
            Some("identity") | None => {
                // No compression
                Ok(body)
            }
            Some(other) => Err(Error::Custom(format!("Unsupported encoding: {}", other))),
        }
    }

    /// Internal request method with retry logic.
    async fn request(&self, method: Method, uri: Uri) -> Result<Response<Body>> {
        self.inner.rate_limiter.wait().await;

        let inner = Arc::clone(&self.inner);

        self.inner
            .retry_policy
            .execute(|| {
                let uri = uri.clone();
                let method = method.clone();
                let inner = Arc::clone(&inner);

                Box::pin(async move {
                    let req = Request::builder()
                        .method(method)
                        .uri(&uri)
                        .header("User-Agent", &inner.user_agent)
                        .header("Accept", "application/json")
                        .header("Accept-Encoding", "gzip, deflate")
                        .header("Host", uri.host().unwrap_or("data.sec.gov"))
                        .body(Body::empty())
                        .map_err(Error::HttpError)?;

                    let response = inner.client.request(req).await.map_err(Error::HyperError)?;

                    match response.status() {
                        StatusCode::OK => Ok(response),
                        StatusCode::TOO_MANY_REQUESTS => {
                            Err(Error::RateLimitExceeded("SEC rate limit exceeded".into()))
                        }
                        StatusCode::NOT_FOUND => Err(Error::NotFound(format!("Not found: {}", uri))),
                        status => Err(Error::InvalidStatus(status)),
                    }
                })
            })
            .await
    }
}
