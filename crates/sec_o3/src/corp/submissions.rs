//! Company submissions and filing history retrieval.
//!
//! This module provides functionality to fetch and filter
//! SEC filing submissions for companies.

use crate::filings::FormType;
use serde::{Deserialize, Serialize};

#[allow(unused)]
const SUBMISSIONS_BASE: &str = "https://data.sec.gov/submissions";

/// Company submissions data structure.
///
/// Contains metadata about a company and its complete filing history.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CompanySubmissions {
    /// Company CIK (10-digit format)
    pub cik: String,
    /// Entity type (e.g., "operating", "non-operating")
    pub entity_type: String,
    /// Standard Industrial Classification code
    pub sic: String,
    /// SIC description
    pub sic_description: String,
    /// Company name
    pub name: String,
    /// Trading ticker symbols
    pub tickers: Option<Vec<String>>,
    /// Stock exchanges where traded
    pub exchanges: Option<Vec<String>>,
    /// Filing history
    pub filings: Filings,
}

/// Container for filing history.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Filings {
    /// Recent filings (most recent first)
    pub recent: RecentFilings,
    /// Historical filing archives
    pub files: Vec<HistoricalFile>,
}

/// Recent filing data arrays.
///
/// Each field is a parallel array where index N corresponds to the Nth filing.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RecentFilings {
    /// Accession numbers
    pub accession_number: Vec<String>,
    /// Filing dates
    pub filing_date: Vec<String>,
    /// Report dates (optional)
    pub report_date: Option<Vec<String>>,
    /// Acceptance timestamps
    pub acceptance_date_time: Vec<String>,
    /// Act under which filed
    pub act: Vec<String>,
    /// Form types
    pub form: Vec<String>,
    /// File numbers
    pub file_number: Vec<String>,
    /// Film numbers
    pub film_number: Vec<String>,
    /// Items reported (for 8-K)
    pub items: Vec<String>,
    /// Filing size in bytes
    pub size: Vec<i64>,
    /// XBRL indicator (1 = true, 0 = false)
    pub is_xbrl: Vec<i32>,
    /// Inline XBRL indicator
    pub is_inline_xbrl: Vec<i32>,
    /// Primary document filename
    pub primary_document: Vec<String>,
    /// Primary document description
    pub primary_doc_description: Vec<String>,
}

/// Historical filing archive metadata.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistoricalFile {
    /// Archive filename
    pub name: String,
    /// Number of filings in archive
    pub filing_count: i32,
    /// Earliest filing date
    pub filing_from: String,
    /// Latest filing date
    pub filing_to: String,
}

/// Fetch company submissions data from SEC API.
///
/// Retrieves all filing submissions for a company.
///
/// # Arguments
///
/// * `cik` - Company CIK (will be normalized)
///
/// # Errors
///
/// Returns an error if:
/// - The CIK is invalid
/// - The network request fails
/// - The response cannot be parsed
///
/// # Examples
///
/// ```rust,no_run
/// use sec_o3::fetch_company_filings;
///
/// #[tokio::main]
/// async fn main() -> Result<(), Box<dyn std::error::Error>> {
///     let submissions = fetch_company_filings("320193").await?;
///
///     println!("Company: {}", submissions.name);
///     println!("Tickers: {:?}", submissions.tickers);
///
///     // List recent 10-K filings
///     for (i, form) in submissions.filings.recent.form.iter().enumerate() {
///         if form == "10-K" {
///             println!("10-K filed on {}", submissions.filings.recent.filing_date[i]);
///         }
///     }
///
///     Ok(())
/// }
/// ```
/// Filter filings by form type.
///
/// Returns a vector of simplified filing records matching the specified form type.
///
/// # Arguments
///
/// * `submissions` - Company submissions data
/// * `form_type` - The form type to filter for
///
/// # Examples
///
/// ```rust,no_run
/// use sec_o3::{fetch_company_filings, filings::FormType};
/// use sec_o3::corp::submissions::filter_by_form_type;
///
/// # async fn example() -> Result<(), Box<dyn std::error::Error>> {
/// let submissions = fetch_company_filings("320193").await?;
/// let ten_ks = filter_by_form_type(&submissions, FormType::TenK);
///
/// for filing in ten_ks {
///     println!("10-K filed on {}: {}", filing.filing_date, filing.accession_number);
/// }
/// # Ok(())
/// # }
/// ```
pub fn filter_by_form_type(submissions: &CompanySubmissions, form_type: FormType) -> Vec<Filing> {
    let form_str = form_type.to_string();
    let recent = &submissions.filings.recent;

    recent
        .form
        .iter()
        .enumerate()
        .filter(|(_, f)| *f == &form_str)
        .map(|(idx, _)| Filing {
            accession_number: recent.accession_number[idx].clone(),
            filing_date: recent.filing_date[idx].clone(),
            form: recent.form[idx].clone(),
            primary_document: recent.primary_document[idx].clone(),
        })
        .collect()
}

/// Simplified filing record.
#[derive(Debug, Clone)]
pub struct Filing {
    /// Accession number
    pub accession_number: String,
    /// Filing date
    pub filing_date: String,
    /// Form type
    pub form: String,
    /// Primary document filename
    pub primary_document: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_submissions_url() {
        let cik = "320193";
        let normalized_cik = crate::normalize_cik(cik).unwrap();
        let url = format!("{}/CIK{}.json", SUBMISSIONS_BASE, normalized_cik);
        assert_eq!(url, "https://data.sec.gov/submissions/CIK0000320193.json");
    }
}
