//! # sec_o3
//!
//! Fast, modern SEC/EDGAR utilities with HTTP/2 client and optional Python bindings.
//!
//! ## Modules
//!
//! - [`download`] - HTTP client, rate limiting, and data fetching
//! - [`parse`] - Document parsing and text extraction
//! - [`errors`] - Unified error handling
//! - [`utils`] - Shared utility functions
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
//! use sec_o3::download::{Client, ticker_to_cik};
//!
//! #[tokio::main]
//! async fn main() -> sec_o3::Result<()> {
//!     // Look up ticker
//!     let cik = ticker_to_cik("AAPL").await?;
//!
//!     // Create client
//!     let client = Client::new("MyApp", "contact@example.com");
//!
//!     // Fetch company data
//!     let url = format!("https://data.sec.gov/submissions/CIK{}.json", cik);
//!     let data = client.get_json(&url).await?;
//!
//!     Ok(())
//! }
//! ```

pub mod download;
pub mod errors;
pub mod parse;
pub mod utils;

#[cfg(feature = "python")]
pub mod python;

// Re-export commonly used types at crate root for convenience
pub use download::Client;
pub use errors::{Error, Result};
pub use parse::{parse_html, parse_json, Document, DocumentFormat};
pub use utils::str_to_utc_datetime;

/// Library version
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Library name
pub const NAME: &str = env!("CARGO_PKG_NAME");

/// Root directory
pub const ROOT_DIR: &str = env!("CARGO_MANIFEST_DIR");

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
        let _client: Client = Client::new("Test", "test@example.com");
    }
}
