//! edga_rs: Fast SEC/EDGAR helpers with modern Hyper client and optional Python bindings.
//!
//! # Architecture
//!
//! ## Modules
//! - `client` - HTTP client with rate limiting and retry logic
//! - `data` - Company data retrieval (CIK lookup, submissions, facts)
//! - `filings` - SEC form types and metadata
//! - `parse` - Document parsing (HTML, JSON, XBRL)
//! - `utils` - Utility functions for URL construction
//!
//! ## Error Handling
//! This crate uses a standardized error handling pattern with module-specific `Result` types.
//!
//! ## Features
//! - `python` - Python bindings via PyO3
//! - `cache` - Disk caching support (requires additional dependencies)
//! - `full` - Enable all features

pub mod client;
pub mod corp;
pub mod errors;
pub mod filings;
pub mod parse;
pub mod utils;

#[cfg(feature = "cache")]
pub mod cache;

#[cfg(feature = "python")]
pub mod python;

// Re-export commonly used types
pub use client::SecClient;
pub use corp::{
    cik::{get_ticker_cik_map, normalize_cik},
    facts::{fetch_company_facts, CompanyFacts},
    submissions::{fetch_company_filings, CompanySubmissions},
};
pub use errors::{
    DecodeError, FetchError, IngestError, IoError, LookupError, NetworkError, ParseError, ParserError, ValidationError,
};
pub use filings::{is_valid_filing_type, SecFormType};
pub use parse::{
    parse,
    traits::{DataFormat, DocumentParser, ParsedDocument},
    HtmlParser, JsonParser,
};

#[cfg(feature = "cache")]
pub use cache::DiskCache;
