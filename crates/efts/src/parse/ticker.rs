use once_cell::sync::Lazy;
use regex::Regex;
use serde_json::{Map, Value};

static PAREN_PATTERN: Lazy<Regex> = Lazy::new(|| Regex::new(r"\(([^)]+)\)").expect("valid regex"));

pub(crate) fn extract_tickers(source: &Map<String, Value>, company_name: &str) -> Vec<String> {
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
            for item in value.split(|ch: char| ch == ',' || ch == '/' || ch.is_whitespace()) {
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

pub(crate) fn extract_tickers_from_company(company_name: &str) -> Vec<String> {
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

pub(crate) fn normalize_ticker(value: &str) -> Option<String> {
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
