/// # sec_o3
///
/// Fast, modern SEC/EDGAR utilities with Hyper HTTP/2 client and optional Python bindings.
///
/// ## Features
///
/// - **High Performance**: Modern async HTTP client with HTTP/2 support
/// - **Rate Limiting**: Automatic SEC API rate limit compliance (10 req/s)
/// - **Retry Logic**: Exponential backoff for transient failures
/// - **Type Safe**: Comprehensive error handling with detailed error types
/// - **Python Bindings**: Optional PyO3 bindings for Python integration
///
/// ## Quick Start
///
/// ```rust,no_run
/// use sec_o3::{Client};
///
/// #[tokio::main]
/// async fn main() -> Result<(), Box<dyn std::error::Error>> {
///     // Look up ticker
///
///     // Fetch company data
///     let client = Client::new("John F. Kennedy", "jfk@<whitehouse>.gov");
///     let facts = sec_o3::get_recent_filings("0001045810").await?;
///
///     Ok(())
/// }
/// ```
///
/// ## Architecture
/// - `client` - HTTP client with rate limiting and retry logic
pub mod client;
/// - `errors` - Unified error handling
pub mod errors;
/// - `filings` - Functions for fetching and downloading filings.
pub mod filings;
/// - `utils` - Utility functions for standardizing dates and retrieving CIKs.
pub mod utils;

#[cfg(feature = "python")]
pub mod python;

pub use client::Client;
pub use errors::{Error, Result};

/// Library version
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Library name
pub const NAME: &str = env!("CARGO_PKG_NAME");

// Root directory
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
        let _client: Client = Client::new("Nic Hill", "nrhill1@gmail.com");
    }
}
