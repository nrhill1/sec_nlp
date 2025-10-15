// src/data/submissions.rs - Company submissions and filings
use crate::client::{Result, SecClient};
use crate::filings::SecFormType;
use serde::{Deserialize, Serialize};

const SUBMISSIONS_BASE: &str = "https://data.sec.gov/submissions";

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CompanySubmissions {
    pub cik: String,
    pub entity_type: String,
    pub sic: String,
    pub sic_description: String,
    pub name: String,
    pub tickers: Option<Vec<String>>,
    pub exchanges: Option<Vec<String>>,
    pub filings: Filings,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Filings {
    pub recent: RecentFilings,
    pub files: Vec<HistoricalFile>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RecentFilings {
    pub accession_number: Vec<String>,
    pub filing_date: Vec<String>,
    pub report_date: Option<Vec<String>>,
    pub acceptance_date_time: Vec<String>,
    pub act: Vec<String>,
    pub form: Vec<String>,
    pub file_number: Vec<String>,
    pub film_number: Vec<String>,
    pub items: Vec<String>,
    pub size: Vec<i64>,
    pub is_xbrl: Vec<i32>,
    pub is_inline_xbrl: Vec<i32>,
    pub primary_document: Vec<String>,
    pub primary_doc_description: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistoricalFile {
    pub name: String,
    pub filing_count: i32,
    pub filing_from: String,
    pub filing_to: String,
}

/// Fetch company submissions data from SEC API
pub async fn fetch_company_filings(cik: &str) -> Result<CompanySubmissions> {
    let client = SecClient::new();
    let normalized_cik = crate::corp::cik::normalize_cik(cik);
    let url = format!("{}/CIK{}.json", SUBMISSIONS_BASE, normalized_cik);

    client.fetch_and_parse_json(&url).await
}

/// Filter filings by form type
pub fn filter_by_form_type(
    submissions: &CompanySubmissions,
    form_type: SecFormType,
) -> Vec<Filing> {
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

#[derive(Debug, Clone)]
pub struct Filing {
    pub accession_number: String,
    pub filing_date: String,
    pub form: String,
    pub primary_document: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_submissions_url() {
        let cik = "320193";
        let url = format!(
            "{}/CIK{}.json",
            SUBMISSIONS_BASE,
            crate::corp::cik::normalize_cik(cik)
        );
        assert_eq!(url, "https://data.sec.gov/submissions/CIK0000320193.json");
    }
}
