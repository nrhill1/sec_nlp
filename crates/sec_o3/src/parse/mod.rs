//! Parse module - Document parsing and text extraction
//!
//! This module handles parsing of SEC documents in various formats:
//! - HTML documents
//! - JSON submissions
//! - XML filings
//! - Plain text documents
//!
//! # Examples
//!
//! ```
//! use sec_o3::parse::{parse_html, parse_json};
//!
//! let html = "<html><body>FORM 10-K</body></html>";
//! let doc = parse_html(html).unwrap();
//! assert_eq!(doc.form_type, "10-K");
//! ```

pub mod document;
pub mod html;
pub mod json;

// Re-export commonly used types
// Re-export errors for convenience
pub use document::{Document, DocumentFormat};
pub use html::parse_html;
pub use json::parse_json;

pub use crate::errors::{Error, Result};
