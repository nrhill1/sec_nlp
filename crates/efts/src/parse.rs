use chrono::{NaiveDate, Utc};
use once_cell::sync::Lazy;
use regex::Regex;
use serde_json::{Map, Value};

use crate::models::{SearchHit, SearchResponse};

const INSIDER_FORMS: [&str; 6] = ["3", "3/A", "4", "4/A", "5", "5/A"];
const COMPANY_KEYWORDS: [&str; 24] = [
    " INC",
    " INC.",
    " CORP",
    " CORPORATION",
    " LTD",
    " LIMITED",
    " LLC",
    " PLC",
    " LP",
    " L.P.",
    " LLP",
    " CO",
    " COMPANY",
    " HOLDINGS",
    " GROUP",
    " TRUST",
    " FUND",
    " RESOURCES",
    " MINING",
    " MATERIALS",
    " ENERGY",
    " TECHNOLOGIES",
    " SYSTEMS",
    " ENTERPRISES",
];

static CIK_PATTERN: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(?i)\bCIK\s*(\d{1,10})\b").expect("valid regex"));
static PAREN_PATTERN: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"\(([^)]+)\)").expect("valid regex"));

pub(crate) fn parse_response(data: &Value, query: &str) -> SearchResponse {
    let empty = Map::new();
    let hits_data = data
        .get("hits")
        .and_then(|v| v.as_object())
        .unwrap_or(&empty);
    let total = extract_total(hits_data);
    let raw_hits = hits_data
        .get("hits")
        .and_then(|v| v.as_array())
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    let mut hits = Vec::new();
    for raw_hit in raw_hits {
        hits.push(parse_hit(raw_hit));
    }
    let query_data = data
        .get("query")
        .and_then(|v| v.as_object())
        .unwrap_or(&empty);
    let start = get_u32(query_data, "from", 0);
    let limit = get_u32(query_data, "size", 10);
    SearchResponse {
        query: query.to_string(),
        total,
        hits,
        start,
        limit,
    }
}

fn parse_hit(raw: &Value) -> SearchHit {
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
        filed_date,
        file_number,
        film_number,
        snippet,
        score,
        filing_url: None,
    }
}

fn get_str(data: &Map<String, Value>, key: &str, default: &str) -> String {
    data.get(key)
        .and_then(|v| v.as_str())
        .unwrap_or(default)
        .to_string()
}

fn get_optional_str(data: &Map<String, Value>, key: &str) -> Option<String> {
    data.get(key)
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
}

fn get_u32(data: &Map<String, Value>, key: &str, default: u32) -> u32 {
    data.get(key)
        .and_then(|v| v.as_u64().or_else(|| v.as_f64().map(|f| f as u64)))
        .map(|v| v as u32)
        .unwrap_or(default)
}

fn get_f64(data: &Value, key: &str, default: f64) -> f64 {
    data.get(key)
        .and_then(|v| v.as_f64().or_else(|| v.as_i64().map(|i| i as f64)))
        .unwrap_or(default)
}

fn extract_total(hits_data: &Map<String, Value>) -> u64 {
    match hits_data.get("total") {
        Some(Value::Object(total)) => total
            .get("value")
            .and_then(|v| v.as_u64().or_else(|| v.as_f64().map(|f| f as u64)))
            .unwrap_or(0),
        Some(Value::Number(number)) => number
            .as_u64()
            .or_else(|| number.as_f64().map(|f| f as u64))
            .unwrap_or(0),
        _ => 0,
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
        let trimmed = if value.len() >= 10 { &value[..10] } else { value };
        if let Ok(date) = NaiveDate::parse_from_str(trimmed, "%Y-%m-%d") {
            return date.format("%Y-%m-%d").to_string();
        }
    }
    Utc::now().date_naive().format("%Y-%m-%d").to_string()
}

fn extract_accession(source: &Map<String, Value>) -> String {
    let raw = source
        .get("adsh")
        .or_else(|| source.get("accession_number"));
    let accession = raw.and_then(value_to_string).unwrap_or_default();
    if !accession.is_empty() && !accession.contains('-') && accession.len() == 18
    {
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

fn extract_company_name(source: &Map<String, Value>) -> String {
    let form_type = get_str(source, "form", "");
    let normalized_form = form_type.replace(' ', "").to_uppercase();
    let company_raw = source.get("company");
    let display_names = extract_display_names(source.get("display_names"));

    if is_insider_form(&normalized_form) {
        if let Some(Value::String(company_name)) = company_raw {
            let trimmed = company_name.trim();
            if !trimmed.is_empty() {
                return trimmed.to_string();
            }
        }
        if let Some(best) = best_display_name(&display_names) {
            return best;
        }
    }

    if let Some(first) = display_names.first() {
        return first.clone();
    }
    if let Some(raw) = company_raw.and_then(value_to_string) {
        return raw;
    }
    String::new()
}

fn extract_display_names(value: Option<&Value>) -> Vec<String> {
    match value.and_then(|v| v.as_array()) {
        Some(values) => values
            .iter()
            .filter_map(|item| item.as_str().map(|s| s.to_string()))
            .collect(),
        None => Vec::new(),
    }
}

fn best_display_name(display_names: &[String]) -> Option<String> {
    let mut best_score = -100;
    let mut best_name: Option<String> = None;
    for item in display_names {
        let name = item.trim();
        if name.is_empty() {
            continue;
        }
        let upper = name.to_uppercase();
        let mut score = 0;
        if !upper.contains("CIK") {
            score += 2;
        }
        if name.contains('(') && name.contains(')') && !upper.contains("CIK") {
            score += 1;
        }
        if name.contains(',') {
            score -= 1;
        }
        for keyword in COMPANY_KEYWORDS {
            if upper.contains(keyword) {
                score += 2;
                break;
            }
        }
        if score > best_score {
            best_score = score;
            best_name = Some(name.to_string());
        }
    }
    best_name
}

fn extract_tickers(source: &Map<String, Value>, company_name: &str) -> Vec<String> {
    let mut tickers = Vec::new();
    match source.get("tickers") {
        Some(Value::Array(items)) => {
            for item in items {
                if let Some(ticker) = item.as_str() {
                    append_ticker(&mut tickers, ticker);
                }
            }
        }
        Some(Value::String(value)) => {
            for item in value.split(|ch: char| {
                ch == ',' || ch == '/' || ch.is_whitespace()
            }) {
                append_ticker(&mut tickers, item);
            }
        }
        _ => {}
    }
    if let Some(Value::String(value)) = source.get("ticker") {
        append_ticker(&mut tickers, value);
    }
    if tickers.is_empty() {
        tickers = extract_tickers_from_company(company_name);
    }
    tickers
}

fn extract_tickers_from_company(company_name: &str) -> Vec<String> {
    let mut tickers = Vec::new();
    if company_name.is_empty() {
        return tickers;
    }
    for caps in PAREN_PATTERN.captures_iter(company_name) {
        if let Some(match_value) = caps.get(1).map(|m| m.as_str()) {
            for raw in match_value.split([',', '/']) {
                let cleaned = raw.trim();
                if cleaned.is_empty() {
                    continue;
                }
                if cleaned.to_uppercase().contains("CIK") {
                    continue;
                }
                append_ticker(&mut tickers, cleaned);
            }
        }
    }
    tickers
}

fn append_ticker(tickers: &mut Vec<String>, value: &str) {
    if let Some(cleaned) = normalize_ticker(value) {
        if !tickers.contains(&cleaned) {
            tickers.push(cleaned);
        }
    }
}

fn normalize_ticker(value: &str) -> Option<String> {
    let mut cleaned = value.trim().to_uppercase();
    cleaned = cleaned
        .trim_matches(|ch: char| matches!(ch, '(' | ')' | '[' | ']' | '{' | '}'))
        .to_string();
    if cleaned.is_empty() {
        return None;
    }
    if cleaned.contains("CIK") {
        return None;
    }
    if let Some(index) = cleaned.rfind(':') {
        let suffix = cleaned[index + 1..].trim();
        if !suffix.is_empty() {
            cleaned = suffix.to_string();
        }
    }
    if !cleaned.chars().any(|ch| ch.is_ascii_alphabetic()) {
        return None;
    }
    if cleaned.len() > 10 {
        return None;
    }
    Some(cleaned)
}

fn extract_cik(
    source: &Map<String, Value>,
    company_name: &str,
    accession: &str,
) -> String {
    if let Some(cik) = coerce_cik(source.get("cik")) {
        return cik;
    }
    if let Some(Value::Array(items)) = source.get("ciks") {
        for item in items {
            if let Some(cik) = coerce_cik(Some(item)) {
                return cik;
            }
        }
    }
    if let Some(cik) = extract_cik_from_company(company_name) {
        return cik;
    }
    if let Some(cik) = extract_cik_from_accession(accession) {
        return cik;
    }
    "0000000000".to_string()
}

fn coerce_cik(value: Option<&Value>) -> Option<String> {
    let value = value?;
    if value.is_null() || value.is_boolean() {
        return None;
    }
    if let Some(number) = value.as_i64() {
        return coerce_cik_str(&number.to_string());
    }
    if let Some(number) = value.as_u64() {
        return coerce_cik_str(&number.to_string());
    }
    if let Some(number) = value.as_f64() {
        return coerce_cik_str(&format!("{}", number as i64));
    }
    if let Some(text) = value.as_str() {
        return coerce_cik_str(text);
    }
    None
}

fn coerce_cik_str(value: &str) -> Option<String> {
    let digits: String = value.chars().filter(|ch| ch.is_ascii_digit()).collect();
    if digits.is_empty() {
        return None;
    }
    let trimmed = if digits.len() > 10 {
        digits[digits.len() - 10..].to_string()
    } else {
        digits
    };
    let cik = format!("{:0>10}", trimmed);
    if cik == "0000000000" {
        None
    } else {
        Some(cik)
    }
}

fn extract_cik_from_company(company_name: &str) -> Option<String> {
    if company_name.is_empty() {
        return None;
    }
    let match_value = CIK_PATTERN.captures(company_name)?;
    coerce_cik_str(&match_value[1])
}

fn extract_cik_from_accession(accession: &str) -> Option<String> {
    if accession.is_empty() {
        return None;
    }
    let prefix = accession.split('-').next().unwrap_or("");
    coerce_cik_str(prefix)
}

fn value_to_string(value: &Value) -> Option<String> {
    if let Some(text) = value.as_str() {
        return Some(text.to_string());
    }
    if let Some(number) = value.as_i64() {
        return Some(number.to_string());
    }
    if let Some(number) = value.as_u64() {
        return Some(number.to_string());
    }
    if let Some(number) = value.as_f64() {
        return Some((number as i64).to_string());
    }
    None
}

fn is_insider_form(form_type: &str) -> bool {
    INSIDER_FORMS.contains(&form_type)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn parse_response_matches_sample() {
        let sample = json!({
            "query": {"from": 0, "size": 10, "q": "warranty accrual"},
            "hits": {
                "total": {"value": 42},
                "hits": [
                    {
                        "_score": 15.5,
                        "_source": {
                            "adsh": "0001234567-24-000001",
                            "cik": "1234567",
                            "display_names": ["Apple Inc."],
                            "form": "10-K",
                            "file_date": "2024-01-15"
                        },
                        "highlight": {"text": ["warranty <em>accrual</em> provisions"]}
                    },
                    {
                        "_score": 12.3,
                        "_source": {
                            "adsh": "0009876543-24-000002",
                            "cik": "9876543",
                            "display_names": ["Microsoft Corporation"],
                            "form": "10-Q",
                            "file_date": "2024-02-20"
                        },
                        "highlight": {"text": ["product <em>warranty</em> reserves"]}
                    }
                ]
            }
        });

        let response = parse_response(&sample, "warranty accrual");

        assert_eq!(response.total, 42);
        assert_eq!(response.hits.len(), 2);
        assert_eq!(response.hits[0].company_name, "Apple Inc.");
        assert_eq!(response.hits[0].form_type, "10-K");
        assert_eq!(response.hits[0].score, 15.5);
    }

    #[test]
    fn parse_response_empty_hits() {
        let sample = json!({
            "query": {"from": 0, "size": 10, "q": "nope"},
            "hits": {"total": {"value": 0}, "hits": []}
        });

        let response = parse_response(&sample, "nope");

        assert_eq!(response.total, 0);
        assert!(response.hits.is_empty());
    }

    #[test]
    fn parse_hit_normalizes_accession_and_ticker() {
        let raw = json!({
            "_score": 15.5,
            "_source": {
                "adsh": "000123456724000001",
                "cik": "1234567",
                "display_names": ["Apple Inc. (AAPL)"],
                "form": "10-K",
                "file_date": "2024-01-15"
            },
            "highlight": {"text": ["warranty <em>accrual</em>"]}
        });

        let hit = parse_hit(&raw);

        assert_eq!(hit.accession_number, "0001234567-24-000001");
        assert_eq!(hit.tickers, vec!["AAPL"]);
        assert!(hit.snippet.contains("warranty"));
    }

    #[test]
    fn parse_hit_prefers_issuer_for_insider_forms() {
        let raw = json!({
            "_score": 12.1,
            "_source": {
                "adsh": "0001801368-24-000123",
                "cik": "0002006182",
                "company": "MP Materials Corp",
                "display_names": [
                    "Dhillon Mannik S. (CIK 0002006182)",
                    "MP Materials Corp (MP)"
                ],
                "form": "4",
                "file_date": "2024-01-15"
            }
        });

        let hit = parse_hit(&raw);

        assert_eq!(hit.company_name, "MP Materials Corp");
    }

    #[test]
    fn extract_tickers_from_company_filters_cik() {
        let tickers = extract_tickers_from_company(
            "Example Corp (CIK 0001234567) (EXM, EXM.A)",
        );

        assert_eq!(tickers, vec!["EXM", "EXM.A"]);
    }

    #[test]
    fn normalize_ticker_rejects_non_alpha() {
        assert_eq!(normalize_ticker("1234"), None);
        assert_eq!(normalize_ticker("NYSE:V"), Some("V".to_string()));
        assert_eq!(normalize_ticker(" (AAPL) "), Some("AAPL".to_string()));
    }
}
