//! Company XBRL facts retrieval.
//!
//! This module provides functionality to fetch and parse structured
//! XBRL (eXtensible Business Reporting Language) data from the SEC.

use crate::client::SecClient;
use crate::errors::Result;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

const FACTS_BASE: &str = "https://data.sec.gov/api/xbrl/companyfacts";

/// Company XBRL facts data structure.
///
/// Contains all structured financial data reported by a company
/// in XBRL format, organized by taxonomy and concept.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompanyFacts {
    /// Company CIK number
    pub cik: i32,
    /// Company entity name
    #[serde(rename = "entityName")]
    pub entity_name: String,
    /// Facts organized by taxonomy (e.g., "us-gaap", "ifrs-full")
    pub facts: HashMap<String, Taxonomy>,
}

/// XBRL taxonomy containing financial concepts.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Taxonomy {
    /// Financial concepts within this taxonomy
    #[serde(flatten)]
    pub concepts: HashMap<String, Concept>,
}

/// XBRL concept (e.g., "Revenues", "Assets", "NetIncome").
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Concept {
    /// Human-readable label for the concept
    pub label: String,
    /// Description of the concept
    pub description: String,
    /// Facts organized by unit of measurement
    pub units: HashMap<String, Vec<Fact>>,
}

/// Individual XBRL fact (a single data point).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Fact {
    /// End date of the reporting period
    pub end: String,
    /// The actual value
    pub val: serde_json::Value,
    /// Accession number of the filing
    pub accn: String,
    /// Fiscal year
    pub fy: i32,
    /// Fiscal period (e.g., "Q1", "FY")
    pub fp: String,
    /// Form type (e.g., "10-K", "10-Q")
    pub form: String,
    /// Filing date
    pub filed: String,
    /// Optional frame identifier (e.g., "CY2023Q1")
    #[serde(skip_serializing_if = "Option::is_none")]
    pub frame: Option<String>,
}

/// Fetch company XBRL facts from SEC API.
///
/// Retrieves all structured financial data for a company.
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
/// use edgars::fetch_company_facts;
///
/// #[tokio::main]
/// async fn main() -> Result<(), Box<dyn std::error::Error>> {
///     let facts = fetch_company_facts("320193").await?;
///     
///     println!("Company: {}", facts.entity_name);
///     
///     // Access revenue data
///     if let Some(us_gaap) = facts.facts.get("us-gaap") {
///         if let Some(revenues) = us_gaap.concepts.get("Revenues") {
///             println!("Revenue label: {}", revenues.label);
///             
///             if let Some(usd_data) = revenues.units.get("USD") {
///                 for fact in usd_data.iter().take(3) {
///                     println!("  {} (FY {}): ${}", fact.form, fact.fy, fact.val);
///                 }
///             }
///         }
///     }
///     
///     Ok(())
/// }
/// ```
pub async fn fetch_company_facts(cik: &str) -> Result<CompanyFacts> {
    let client = SecClient::new();
    let normalized_cik = crate::corp::cik::normalize_cik(cik);
    let url = format!("{}/CIK{}.json", FACTS_BASE, normalized_cik);

    client.fetch_json(&url).await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_facts_url() {
        let cik = "320193";
        let url = format!("{}/CIK{}.json", FACTS_BASE, crate::corp::cik::normalize_cik(cik));
        assert_eq!(url, "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json");
    }
}
