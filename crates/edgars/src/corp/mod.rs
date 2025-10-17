//! Corporate entity utilities.
//!
//! This module provides functionality for working with corporate identifiers
//! and entity information from SEC filings.
//!
//! # Submodules
//!
//! * [`cik`] - CIK (Central Index Key) normalization and validation
//! * [`facts`] - Company facts data structures and retrieval
//! * [`submissions`] - Company submission data structures and retrieval

pub mod cik;
pub mod facts;
pub mod submissions;

// Re-export commonly used functions for convenience
pub use cik::normalize_cik;
