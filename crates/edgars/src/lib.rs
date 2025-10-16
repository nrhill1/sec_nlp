// src/lib.rs
//! # edgars
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
//! ```rust
//! use edgars::{SecClient, normalize_cik, get_ticker_map};
//!
//! #[tokio::main]
//! async fn main() -> Result<(), Box<dyn std::error::Error>> {
//!     // Look up ticker
//!     let map = get_ticker_map().await?;
//!     let cik = map.get("AAPL").unwrap();
//!     
//!     // Fetch company data
//!     let client = SecClient::new();
//!     let facts = edgars::fetch_company_facts(cik).await?;
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
pub mod corp;
pub mod errors;
pub mod filings;
pub mod parse;
pub mod utils;

#[cfg(feature = "python")]
pub mod python;

// Re-export commonly used types at crate root
pub use client::SecClient;
pub use corp::{
    cik::{get_ticker_map, is_valid_cik, normalize_cik, ticker_to_cik},
    facts::{fetch_company_facts, CompanyFacts},
    submissions::{fetch_company_filings, CompanySubmissions},
};
pub use errors::{EdgarError, Result};
pub use filings::{is_valid_filing_type, FormType};
pub use parse::{parse_auto, parse_html, parse_json, parse_text, Document, Format};
pub use utils::{build_document_url, build_filing_url, build_full_text_url};

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
        assert_eq!(NAME, "edgars");
    }

    #[test]
    fn test_public_exports() {
        // Ensure main exports compile
        let _client: SecClient = SecClient::new();
        let _cik = normalize_cik("320193");
    }
}
