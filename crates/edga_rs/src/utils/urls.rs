// src/utils/urls.rs - URL construction helpers
use crate::corp::cik::normalize_cik;

const ARCHIVES_BASE: &str = "https://www.sec.gov/Archives/edgar/data";

/// Build URL for a filing index page
pub fn build_filing_url(cik: &str, accession_number: &str) -> String {
    let normalized_cik = normalize_cik(cik);
    let accession_no_dashes = accession_number.replace('-', "");

    format!(
        "{}/{}/{}-index.html",
        ARCHIVES_BASE,
        normalized_cik.trim_start_matches('0'),
        accession_no_dashes
    )
}

/// Build URL for a specific document
pub fn build_document_url(cik: &str, accession_number: &str, document: &str) -> String {
    let normalized_cik = normalize_cik(cik);
    let accession_no_dashes = accession_number.replace('-', "");

    format!(
        "{}/{}/{}/{}",
        ARCHIVES_BASE,
        normalized_cik.trim_start_matches('0'),
        accession_no_dashes,
        document
    )
}

/// Build URL for full text filing
pub fn build_full_text_url(cik: &str, accession_number: &str) -> String {
    let normalized_cik = normalize_cik(cik);

    format!(
        "{}/{}/{}.txt",
        ARCHIVES_BASE,
        normalized_cik.trim_start_matches('0'),
        accession_number
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_build_filing_url() {
        let url = build_filing_url("320193", "0000320193-23-000077");
        assert_eq!(
            url,
            "https://www.sec.gov/Archives/edgar/data/320193/000032019323000077-index.html"
        );
    }

    #[test]
    fn test_build_document_url() {
        let url = build_document_url("320193", "0000320193-23-000077", "aapl-20230930.htm");
        assert_eq!(
            url,
            "https://www.sec.gov/Archives/edgar/data/320193/000032019323000077/aapl-20230930.htm"
        );
    }

    #[test]
    fn test_build_full_text_url() {
        let url = build_full_text_url("320193", "0000320193-23-000077");
        assert_eq!(
            url,
            "https://www.sec.gov/Archives/edgar/data/320193/0000320193-23-000077.txt"
        );
    }
}
