use chrono::NaiveDate;
use serde_json::{Map, Value};

use crate::models::SearchHit;

use super::cik::extract_cik;
use super::company::extract_company_name;
use super::ticker::extract_tickers;
use super::util::{get_f64, get_optional_str, get_str, value_to_string};

pub(crate) fn parse_hit(raw: &Value) -> SearchHit {
    let empty = Map::new();
    let source = raw
        .get("_source")
        .and_then(|v| v.as_object())
        .unwrap_or(&empty);
    let snippet = extract_snippet(raw);
    let filed_date = extract_filed_date(source);
    let accession = extract_accession(source);
    let company_name = extract_company_name(source);
    let tickers = extract_tickers(source, &company_name);
    let cik = extract_cik(source, &company_name, &accession);
    let form_type = get_str(source, "form", "");
    let file_number = get_optional_str(source, "file_num");
    let film_number = get_optional_str(source, "film_num");
    let score = get_f64(raw, "_score", 0.0);
    SearchHit {
        accession_number: accession,
        cik,
        company_name,
        tickers,
        form_type,
        filed_date_str: filed_date,
        file_number,
        film_number,
        snippet,
        score,
        filing_url: get_optional_str(source, "filing_url")
            .or_else(|| get_optional_str(source, "link")),
    }
}

fn extract_snippet(raw: &Value) -> String {
    let highlight = match raw.get("highlight").and_then(|v| v.as_object()) {
        Some(value) => value,
        None => return String::new(),
    };
    let snippets = match highlight.get("text").and_then(|v| v.as_array()) {
        Some(value) => value,
        None => return String::new(),
    };
    let mut parts = Vec::new();
    for item in snippets.iter().take(3) {
        if let Some(text) = item.as_str() {
            parts.push(text.to_string());
        } else {
            parts.push(item.to_string());
        }
    }
    parts.join(" ... ")
}

fn extract_filed_date(source: &Map<String, Value>) -> String {
    let filed = source
        .get("file_date")
        .and_then(|v| v.as_str())
        .or_else(|| source.get("filed").and_then(|v| v.as_str()));
    if let Some(value) = filed {
        let trimmed = if value.len() >= 10 {
            &value[..10]
        } else {
            value
        };
        if let Ok(date) = NaiveDate::parse_from_str(trimmed, "%Y-%m-%d") {
            return date.format("%Y-%m-%d").to_string();
        }
    }
    String::new()
}

fn extract_accession(source: &Map<String, Value>) -> String {
    let raw = source
        .get("adsh")
        .or_else(|| source.get("accession_number"));
    let accession = raw.and_then(value_to_string).unwrap_or_default();
    if !accession.is_empty() && !accession.contains('-') && accession.len() == 18 {
        format!(
            "{}-{}-{}",
            &accession[0..10],
            &accession[10..12],
            &accession[12..]
        )
    } else {
        accession
    }
}
