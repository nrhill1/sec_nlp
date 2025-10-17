//! Parsing utilities for SEC documents.
//!
//! This module provides functionality for parsing various SEC document formats,
//! including SGML, XML, HTML, and plain text filings.
//!
//! # Document Formats
//!
//! SEC filings can be in multiple formats:
//! - **SGML**: Legacy format (pre-2000s)
//! - **XML/XBRL**: Structured financial data
//! - **HTML**: Modern filings with embedded exhibits
//! - **Plain text**: Header information and indexes
//!
//! # Examples
//!
//! ```no_run
//! use edgars::parse::{extract_document_text, strip_html};
//!
//! let html = "<html><body><p>Financial data...</p></body></html>";
//! let text = strip_html(html);
//! ```

use regex::Regex;
use std::sync::OnceLock;

/// Extract the primary document from a complete submission text file.
///
/// SEC submissions contain multiple documents. This extracts the main filing
/// document from the complete submission text.
///
/// # Arguments
///
/// * `submission_text` - Complete submission text including all documents
///
/// # Returns
///
/// The primary document text, or None if not found.
///
/// # Examples
///
/// ```no_run
/// use edgars::parse::extract_primary_document;
///
/// let submission = std::fs::read_to_string("filing.txt")?;
/// if let Some(document) = extract_primary_document(&submission) {
///     println!("Found primary document");
/// }
/// # Ok::<(), std::io::Error>(())
/// ```
pub fn extract_primary_document(submission_text: &str) -> Option<String> {
    // Pattern for document boundaries in SEC filings
    static DOC_PATTERN: OnceLock<Regex> = OnceLock::new();
    let pattern = DOC_PATTERN
        .get_or_init(|| Regex::new(r"<DOCUMENT>.*?<TYPE>([^\n]+).*?<TEXT>(.*?)</TEXT>.*?</DOCUMENT>").unwrap());

    // Find the first document (usually the primary filing)
    pattern
        .captures(submission_text)
        .and_then(|caps| caps.get(2).map(|m| m.as_str().to_string()))
}

/// Strip HTML tags from text.
///
/// Removes all HTML tags and decodes common HTML entities.
///
/// # Arguments
///
/// * `html` - HTML text to strip
///
/// # Returns
///
/// Plain text with HTML removed.
///
/// # Examples
///
/// ```
/// use edgars::parse::strip_html;
///
/// let html = "<p>Hello <b>world</b>!</p>";
/// assert_eq!(strip_html(html), "Hello world!");
/// ```
pub fn strip_html(html: &str) -> String {
    static HTML_TAG_PATTERN: OnceLock<Regex> = OnceLock::new();
    let pattern = HTML_TAG_PATTERN.get_or_init(|| Regex::new(r"<[^>]+>").unwrap());

    let text = pattern.replace_all(html, " ");

    // Decode common HTML entities
    let text = text
        .replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'");

    // Normalize whitespace
    normalize_whitespace(&text)
}

/// Normalize whitespace in text.
///
/// Replaces multiple whitespace characters with a single space
/// and trims leading/trailing whitespace.
///
/// # Arguments
///
/// * `text` - Text to normalize
///
/// # Returns
///
/// Text with normalized whitespace.
///
/// # Examples
///
/// ```
/// use edgars::parse::normalize_whitespace;
///
/// let text = "Hello    world\n\n\ntest";
/// assert_eq!(normalize_whitespace(text), "Hello world test");
/// ```
pub fn normalize_whitespace(text: &str) -> String {
    static WHITESPACE_PATTERN: OnceLock<Regex> = OnceLock::new();
    let pattern = WHITESPACE_PATTERN.get_or_init(|| Regex::new(r"\s+").unwrap());

    pattern.replace_all(text, " ").trim().to_string()
}

/// Extract section from filing by header pattern.
///
/// Finds a section in an SEC filing by matching a header pattern
/// and extracting text until the next section header.
///
/// # Arguments
///
/// * `text` - Filing text
/// * `section_header` - Regex pattern for the section header
///
/// # Returns
///
/// The section text, or None if not found.
///
/// # Examples
///
/// ```
/// use edgars::parse::extract_section;
///
/// let filing = "ITEM 1. BUSINESS\n\nWe are a company...\n\nITEM 2. PROPERTIES";
/// let section = extract_section(filing, r"ITEM\s+1\.\s+BUSINESS");
/// assert!(section.is_some());
/// ```
pub fn extract_section(text: &str, section_header: &str) -> Option<String> {
    let pattern = Regex::new(section_header).ok()?;
    let start_match = pattern.find(text)?;
    let start = start_match.start();

    // Find the next section header (ITEM followed by a number)
    static NEXT_SECTION: OnceLock<Regex> = OnceLock::new();
    let next_pattern = NEXT_SECTION.get_or_init(|| Regex::new(r"\n\s*ITEM\s+\d+[A-Z]?\.").unwrap());

    let end = next_pattern
        .find(&text[start + start_match.len()..])
        .map(|m| start + start_match.len() + m.start())
        .unwrap_or(text.len());

    Some(text[start..end].to_string())
}

/// Extract tabular data from text.
///
/// Identifies table-like structures in plain text and returns them
/// as a 2D vector of strings.
///
/// # Arguments
///
/// * `text` - Text containing tables
/// * `min_columns` - Minimum number of columns to consider as a table
///
/// # Returns
///
/// Vector of tables, where each table is a vector of rows,
/// and each row is a vector of cells.
pub fn extract_tables(text: &str, min_columns: usize) -> Vec<Vec<Vec<String>>> {
    let mut tables = Vec::new();
    let lines: Vec<&str> = text.lines().collect();

    let mut current_table: Vec<Vec<String>> = Vec::new();

    for line in lines {
        // Simple heuristic: lines with multiple consecutive spaces might be table rows
        let cells: Vec<String> = line
            .split_whitespace()
            .filter(|s| !s.is_empty())
            .map(|s| s.to_string())
            .collect();

        if cells.len() >= min_columns {
            current_table.push(cells);
        } else if !current_table.is_empty() {
            // End of table
            tables.push(current_table.clone());
            current_table.clear();
        }
    }

    if !current_table.is_empty() {
        tables.push(current_table);
    }

    tables
}

/// Remove SEC header information from filing text.
///
/// SEC filings begin with header information before the actual document.
/// This function removes that header.
///
/// # Arguments
///
/// * `text` - Complete filing text
///
/// # Returns
///
/// Filing text with header removed.
pub fn remove_sec_header(text: &str) -> String {
    // Header typically ends with a line of dashes or equals signs
    static HEADER_END: OnceLock<Regex> = OnceLock::new();
    let pattern = HEADER_END.get_or_init(|| Regex::new(r"\n[-=]{40,}\n").unwrap());

    pattern
        .find(text)
        .map(|m| text[m.end()..].to_string())
        .unwrap_or_else(|| text.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_strip_html() {
        let html = "<html><body><p>Hello <b>world</b>!</p></body></html>";
        let text = strip_html(html);
        assert!(text.contains("Hello"));
        assert!(text.contains("world"));
        assert!(!text.contains("<"));
    }

    #[test]
    fn test_normalize_whitespace() {
        let text = "Hello    world\n\n\ntest";
        assert_eq!(normalize_whitespace(text), "Hello world test");
    }

    #[test]
    fn test_strip_html_entities() {
        let html = "AT&amp;T &nbsp; Test &lt;tag&gt;";
        let text = strip_html(html);
        assert_eq!(text, "AT&T Test <tag>");
    }

    #[test]
    fn test_extract_section() {
        let filing = "ITEM 1. BUSINESS\n\nWe are a company...\n\nITEM 2. PROPERTIES\n\nWe own...";
        let section = extract_section(filing, r"ITEM\s+1\.\s+BUSINESS");

        assert!(section.is_some());
        let section_text = section.unwrap();
        assert!(section_text.contains("We are a company"));
        assert!(!section_text.contains("We own"));
    }

    #[test]
    fn test_extract_tables() {
        let text = "Header\n2023    100    50\n2022    90     45\n\nFooter";
        let tables = extract_tables(text, 3);

        assert_eq!(tables.len(), 1);
        assert_eq!(tables[0].len(), 2); // 2 rows
        assert_eq!(tables[0][0].len(), 3); // 3 columns
    }
}
