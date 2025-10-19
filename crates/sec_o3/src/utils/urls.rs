//! URL construction utilities for SEC EDGAR resources.
//!
//! This module provides functions to build proper URLs for accessing
//! various SEC filing resources on the EDGAR system.

use crate::errors::Result;

const ARCHIVES_BASE: &str = "https://www.sec.gov/Archives/edgar/data";

/// Build URL for a filing index page.
///
/// Creates a URL to the index page that lists all documents within a filing.
///
/// # Arguments
///
/// * `cik` - Company CIK (will be normalized)
/// * `accession_number` - Accession number (e.g., "0000320193-23-000077")
///
/// # Examples
///
/// ```
/// use sec_o3::build_filing_url;
///
/// let url = build_filing_url("320193", "0000320193-23-000077");
/// assert_eq!(
///     url,
///     "https://www.sec.gov/Archives/edgar/data/320193/000032019323000077-index.html"
/// );
/// ```
pub fn build_filing_url(cik: &str, accession_number: &str) -> Result<String> {
    let accession_no_dashes = accession_number.replace('-', "");

    let filing_url = format!("{}/{}/{}-index.html", ARCHIVES_BASE, cik, accession_no_dashes);

    Ok(filing_url)
}

/// Build URL for a specific document within a filing.
///
/// Creates a URL to access a specific document file within a filing package.
///
/// # Arguments
///
/// * `cik` - Company CIK (will be normalized)
/// * `accession_number` - Accession number (e.g., "0000320193-23-000077")
/// * `document` - Document filename (e.g., "aapl-20230930.htm")
///
/// # Examples
///
/// ```
/// use sec_o3::build_document_url;
///
/// let url = build_document_url("320193", "0000320193-23-000077", "aapl-20230930.htm");
/// assert_eq!(
///     url,
///     "https://www.sec.gov/Archives/edgar/data/320193/000032019323000077/aapl-20230930.htm"
/// );
/// ```
pub fn build_document_url(cik: &str, accession_number: &str, document: &str) -> Result<String> {
    let accession_no_dashes = accession_number.replace('-', "");

    let filing_url = format!("{}/{}/{}/{}", ARCHIVES_BASE, cik, accession_no_dashes, document);

    Ok(filing_url)
}

/// Build URL for the full text filing.
///
/// Creates a URL to access the complete filing as a single text file.
/// This is useful for downloading the entire filing at once.
///
/// # Arguments
///
/// * `cik` - Company CIK (will be normalized)
/// * `accession_number` - Accession number (e.g., "0000320193-23-000077")
///
/// # Examples
///
/// ```
/// use sec_o3::build_full_text_url;
///
/// let url = build_full_text_url("320193", "0000320193-23-000077");
/// assert_eq!(
///     url,
///     "https://www.sec.gov/Archives/edgar/data/320193/0000320193-23-000077.txt"
/// );
/// ```
pub fn build_full_text_url(cik: &str, accession_number: &str) -> Result<String> {
    let full_text_url = format!("{}/{}/{}.txt", ARCHIVES_BASE, cik, accession_number);

    Ok(full_text_url)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_build_filing_url() {
        let url = build_filing_url("320193", "0000320193-23-000077").unwrap();
        assert_eq!(
            url,
            "https://www.sec.gov/Archives/edgar/data/320193/000032019323000077-index.html"
        );
    }

    #[test]
    fn test_build_document_url() {
        let url = build_document_url("320193", "0000320193-23-000077", "aapl-20230930.htm").unwrap();
        assert_eq!(
            url,
            "https://www.sec.gov/Archives/edgar/data/320193/000032019323000077/aapl-20230930.htm"
        );
    }

    #[test]
    fn test_build_full_text_url() {
        let url = build_full_text_url("320193", "0000320193-23-000077").unwrap();
        assert_eq!(
            url,
            "https://www.sec.gov/Archives/edgar/data/320193/0000320193-23-000077.txt"
        );
    }

    #[test]
    fn test_url_builders_normalize_cik() {
        // Should work with non-padded CIK
        let url1 = build_filing_url("320193", "0000320193-23-000077").unwrap();
        let url2 = build_filing_url("0000320193", "0000320193-23-000077").unwrap();

        assert_eq!(url1, url2);
    }
}
