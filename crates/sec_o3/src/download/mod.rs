//! Download module - HTTP client, rate limiting, and SEC data fetching
//!
//! This module handles all aspects of downloading data from SEC EDGAR:
//! - HTTP client with rate limiting and retry logic
//! - Filing downloads and metadata retrieval
//! - CIK/ticker lookups and normalization
//!
//! # Examples
//!
//! ```no_run
//! use sec_o3::download::{Client, ticker_to_cik};
//!
//! #[tokio::main]
//! async fn main() -> sec_o3::Result<()> {
//!     // Create client
//!     let client = Client::new("MyApp", "contact@example.com");
//!
//!     // Look up ticker
//!     let cik = ticker_to_cik("AAPL").await?;
//!
//!     // Fetch data
//!     let url = format!("https://data.sec.gov/submissions/CIK{}.json", cik);
//!     let data = client.get_json(&url).await?;
//!
//!     Ok(())
//! }
//! ```
pub mod client;
pub mod filings;
pub mod rate_limit;
pub mod retry;
pub mod validation;

// Re-export commonly used types
pub use client::Client;
pub use filings::{Filing, Submissions};
pub use rate_limit::RateLimiter;
pub use retry::RetryPolicy;

pub use crate::errors::{Error, Result};
