// src/data/facts.rs - Company XBRL facts
use crate::client::SecClient;
use crate::errors::Result;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

const FACTS_BASE: &str = "https://data.sec.gov/api/xbrl/companyfacts";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompanyFacts {
    pub cik: i32,
    #[serde(rename = "entityName")]
    pub entity_name: String,
    pub facts: HashMap<String, Taxonomy>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Taxonomy {
    #[serde(flatten)]
    pub concepts: HashMap<String, Concept>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Concept {
    pub label: String,
    pub description: String,
    pub units: HashMap<String, Vec<Fact>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Fact {
    pub end: String,
    pub val: serde_json::Value,
    pub accn: String,
    pub fy: i32,
    pub fp: String,
    pub form: String,
    pub filed: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub frame: Option<String>,
}

/// Fetch company XBRL facts from SEC API
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
