//! Document parsing utilities for SEC filings.
//!
//! This module provides functions to parse various document formats including:
//! - HTML documents
//! - JSON data
//! - Plain text filings
//! - Auto-detection of format

pub mod infer;

use crate::errors::{EdgarError, Result};
use crate::filings::FormType;
use scraper::{Html, Selector};
use serde_json::Value;

/// Supported document format types.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Format {
    /// HTML document format
    Html,
    /// JSON data format
    Json,
    /// XML/XBRL format
    Xml,
    /// Plain text format
    Text,
}

impl std::fmt::Display for Format {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Format::Html => write!(f, "HTML"),
            Format::Json => write!(f, "JSON"),
            Format::Xml => write!(f, "XML"),
            Format::Text => write!(f, "Text"),
        }
    }
}

/// Parsed document metadata.
///
/// Contains information extracted from a parsed SEC filing document.
#[derive(Debug, Clone)]
pub struct Document {
    /// The SEC form type (e.g., 10-K, 10-Q, 8-K)
    pub form_type: FormType,
    /// The document format
    pub format: Format,
    /// Optional document title
    pub title: Option<String>,
    /// Size of the document in bytes
    pub size_bytes: usize,
}

/// Parse an HTML document.
///
/// Extracts the form type, title, and other metadata from HTML content.
///
/// # Arguments
///
/// * `input` - HTML content as a string
///
/// # Errors
///
/// Returns an error if the form type cannot be determined.
///
/// # Examples
///
/// ```
/// use edgars::parse::parse_html;
///
/// let html = r#"
/// <html>
/// <head><title>Apple Inc. 10-K</title></head>
/// <body>FORM 10-K</body>
/// </html>
/// "#;
///
/// let doc = parse_html(html).unwrap();
/// assert_eq!(doc.form_type.to_string(), "10-K");
/// assert_eq!(doc.title, Some("Apple Inc. 10-K".to_string()));
/// ```
pub fn parse_html(input: &str) -> Result<Document> {
    let doc = Html::parse_document(input);

    // Extract title
    let title = Selector::parse("title")
        .ok()
        .and_then(|sel| doc.select(&sel).next())
        .map(|el| el.text().collect::<String>().trim().to_string())
        .filter(|s| !s.is_empty());

    // Infer form type
    let form_type = infer::infer_form_type(input).ok_or_else(|| EdgarError::Parse {
        format: "HTML".to_string(),
        reason: "Could not determine SEC form type".to_string(),
    })?;

    Ok(Document {
        form_type,
        format: Format::Html,
        title,
        size_bytes: input.len(),
    })
}

/// Parse a JSON document.
///
/// Extracts metadata from JSON-formatted SEC data.
///
/// # Arguments
///
/// * `input` - JSON content as a string
///
/// # Errors
///
/// Returns an error if the JSON is invalid.
///
/// # Examples
///
/// ```
/// use edgars::parse::parse_json;
///
/// let json = r#"{"submissionType": "8-K", "entityName": "Test Corp"}"#;
///
/// let doc = parse_json(json).unwrap();
/// assert_eq!(doc.form_type.to_string(), "8-K");
/// assert_eq!(doc.title, Some("Test Corp".to_string()));
/// ```
pub fn parse_json(input: &str) -> Result<Document> {
    let value: Value = serde_json::from_str(input)?;

    // Extract title if present
    let title = value
        .get("title")
        .or_else(|| value.get("name"))
        .or_else(|| value.get("entityName"))
        .and_then(|v| v.as_str())
        .map(String::from);

    // Infer form type
    let form_type = infer::infer_form_type(input).unwrap_or(FormType::TenQ); // Default fallback

    Ok(Document {
        form_type,
        format: Format::Json,
        title,
        size_bytes: input.len(),
    })
}

/// Parse a plain text document.
///
/// Extracts metadata from plain text SEC filings.
///
/// # Arguments
///
/// * `input` - Text content as a string
///
/// # Errors
///
/// Returns an error if the form type cannot be determined.
///
/// # Examples
///
/// ```
/// use edgars::parse::parse_text;
///
/// let text = "CONFORMED SUBMISSION TYPE: 10-Q\nPUBLIC DOCUMENT COUNT: 50";
///
/// let doc = parse_text(text).unwrap();
/// assert_eq!(doc.form_type.to_string(), "10-Q");
/// ```
pub fn parse_text(input: &str) -> Result<Document> {
    // Try to infer form type from content
    let form_type = infer::infer_form_type(input).ok_or_else(|| EdgarError::Parse {
        format: "Text".to_string(),
        reason: "Could not determine SEC form type".to_string(),
    })?;

    // Try to extract title from first few lines
    let title = input
        .lines()
        .take(20)
        .find(|line| line.to_uppercase().contains("FORM"))
        .map(|s| s.trim().to_string());

    Ok(Document {
        form_type,
        format: Format::Text,
        title,
        size_bytes: input.len(),
    })
}

/// Auto-detect format and parse document.
///
/// Automatically detects the document format (JSON, HTML, XML, or text)
/// and parses it accordingly.
///
/// # Arguments
///
/// * `input` - Document content as a string
///
/// # Errors
///
/// Returns an error if the format cannot be detected or parsing fails.
///
/// # Examples
///
/// ```
/// use edgars::parse::parse_auto;
///
/// // Automatically detects JSON
/// let json = r#"{"submissionType": "8-K"}"#;
/// let doc = parse_auto(json).unwrap();
/// assert_eq!(doc.format.to_string(), "JSON");
///
/// // Automatically detects HTML
/// let html = "<!DOCTYPE html><html><body>FORM 10-K</body></html>";
/// let doc = parse_auto(html).unwrap();
/// assert_eq!(doc.format.to_string(), "HTML");
/// ```
pub fn parse_auto(input: &str) -> Result<Document> {
    // Try JSON first (fastest to detect)
    if input.trim_start().starts_with('{') || input.trim_start().starts_with('[') {
        if let Ok(doc) = parse_json(input) {
            return Ok(doc);
        }
    }

    // Try HTML
    if input.contains("<!DOCTYPE") || input.contains("<html") || input.contains("<HTML") {
        return parse_html(input);
    }

    // Try XML/XBRL
    if input.trim_start().starts_with("<?xml") {
        return Err(EdgarError::NotImplemented(
            "XBRL/XML parsing not yet implemented".to_string(),
        ));
    }

    // Default to text
    parse_text(input)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_html() {
        let html = r#"
<!DOCTYPE html>
<html>
<head><title>Apple Inc. 10-K</title></head>
<body>
<p>FORM 10-K</p>
</body>
</html>
        "#;

        let doc = parse_html(html).unwrap();
        assert_eq!(doc.format, Format::Html);
        assert_eq!(doc.form_type, FormType::TenK);
        assert_eq!(doc.title, Some("Apple Inc. 10-K".to_string()));
    }

    #[test]
    fn test_parse_json() {
        let json = r#"{"title":"Filing","submissionType":"8-K","cik":"0001234567"}"#;

        let doc = parse_json(json).unwrap();
        assert_eq!(doc.format, Format::Json);
        assert_eq!(doc.form_type, FormType::EightK);
        assert_eq!(doc.title, Some("Filing".to_string()));
    }

    #[test]
    fn test_parse_text() {
        let text = r#"
CONFORMED SUBMISSION TYPE: 10-Q
PUBLIC DOCUMENT COUNT: 50
FILED AS OF DATE: 20231115
        "#;

        let doc = parse_text(text).unwrap();
        assert_eq!(doc.format, Format::Text);
        assert_eq!(doc.form_type, FormType::TenQ);
    }

    #[test]
    fn test_parse_auto_json() {
        let json = r#"{"submissionType":"8-K"}"#;

        let doc = parse_auto(json).unwrap();
        assert_eq!(doc.format, Format::Json);
        assert_eq!(doc.form_type, FormType::EightK);
    }

    #[test]
    fn test_parse_auto_html() {
        let html = r#"<!DOCTYPE html><html><body>FORM 10-K</body></html>"#;

        let doc = parse_auto(html).unwrap();
        assert_eq!(doc.format, Format::Html);
        assert_eq!(doc.form_type, FormType::TenK);
    }

    #[test]
    fn test_parse_auto_text() {
        let text = "CONFORMED SUBMISSION TYPE: 10-Q";

        let doc = parse_auto(text).unwrap();
        assert_eq!(doc.format, Format::Text);
        assert_eq!(doc.form_type, FormType::TenQ);
    }

    #[test]
    fn test_parse_invalid_json() {
        let invalid = r#"{"invalid json"#;

        let result = parse_json(invalid);
        assert!(result.is_err());
    }

    #[test]
    fn test_parse_no_form_type() {
        let html = r#"<html><body>No form type here</body></html>"#;

        let result = parse_html(html);
        assert!(result.is_err());
    }
}
