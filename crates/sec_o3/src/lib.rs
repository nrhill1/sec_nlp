//! # sec_o3
//!
//! Fast, modern SEC/EDGAR utilities with Hyper HTTP/2 client and optional Python bindings.
//!
//! ## Features
//!
//! - **High Performance**: Modern async HTTP client with HTTP/2 support
//! - **Rate Limiting**: Automatic SEC API rate limit compliance (10 req/s)
//! - **Retry Logic**: Exponential backoff for transient failures
//! - **Type Safe**: Comprehensive error handling with detailed error types
//! - **Python Bindings**: Optional PyO3 bindings for Python integration
//!
//! ## Quick Start
//!
//! ```rust,no_run
//! use sec_o3::{Client, normalize_cik, get_ticker_map};
//!
//! #[tokio::main]
//! async fn main() -> Result<(), Box<dyn std::error::Error>> {
//!     // Look up ticker
//!     let map = get_ticker_map().await?;
//!     let cik = map.get("AAPL").unwrap();
//!
//!     // Fetch company data
//!     let client = Client::new();
//!     let facts = sec_o3::fetch_company_facts(cik).await?;
//!
//!     println!("Company: {}", facts.entity_name);
//!     Ok(())
//! }
//! ```
//!
//! ## Architecture
//!
//! - `client` - HTTP client with rate limiting and retry logic
//! - `corp` - Company data (CIK lookup, submissions, XBRL facts)
//! - `filings` - SEC form types and metadata
//! - `parse` - Document parsing (HTML, JSON, text)
//! - `utils` - URL construction helpers
//! - `errors` - Unified error handling

#![warn(missing_docs)]
#![warn(rustdoc::missing_crate_level_docs)]
pub mod client;
pub mod errors;
pub mod filings;
pub mod utils;

#[cfg(feature = "python")]
pub mod python;

pub use client::Client;
pub use errors::{Error, Result};

/// Library version
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Library name
pub const NAME: &str = env!("CARGO_PKG_NAME");

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_version_defined() {
        assert!(!VERSION.is_empty());
    }

    #[test]
    fn test_name_defined() {
        assert_eq!(NAME, "sec_o3");
    }

    #[test]
    fn test_public_exports() {
        // Ensure main exports compile
        let _client: Client = Client::new("Nic Hill", "nrhill1@gmail.com");
    }
}
