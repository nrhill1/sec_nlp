//! # Utility Functions
//!
//! This module provides helper utilities used throughout the `sec_o3` crate,
//! primarily focused on URL and path generation for SEC EDGAR endpoints.
//!
//! ## Overview
//!
//! The `utils` module centralizes small but frequently used helper functions that
//! support consistent URL construction, string formatting, and data access patterns.
//!
//! Currently, it focuses on EDGAR URL building utilities via the [`urls`] submodule:
//!
//! - [`build_document_url`] — Returns the full URL to a specific document (e.g., an `.htm` or `.txt` filing).
//! - [`build_filing_url`] — Constructs a URL for a company’s filing index or individual submission.
//! - [`build_full_text_url`] — Generates the SEC-hosted full-text search endpoint URL for filings.
//!
//! ## Example
//!
//! ```rust
//! use sec_o3::utils::{build_document_url, build_filing_url};
//!
//! let filing_url = build_filing_url("0000320193", "0001193125-23-123456");
//! let doc_url = build_document_url("0000320193", "0001193125-23-123456", "aapl-10k2023.htm");
//!
//! println!("Filing index: {}", filing_url);
//! println!("Document: {}", doc_url);
//! ```
//!
//! These utilities ensure consistent, canonical URL generation that aligns with
//! SEC’s current EDGAR directory structure and can be reused across the downloader,
//! parser, and CLI layers.

pub mod urls;

pub use urls::{build_document_url, build_filing_url, build_full_text_url};
