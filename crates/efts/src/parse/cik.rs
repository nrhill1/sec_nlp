use once_cell::sync::Lazy;
use regex::Regex;
use serde_json::{Map, Value};

static CIK_PATTERN: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(?i)\bCIK\s*(\d{1,10})\b").expect("valid regex"));

pub(crate) fn extract_cik(
    source: &Map<String, Value>,
    company_name: &str,
    _accession: &str,
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
