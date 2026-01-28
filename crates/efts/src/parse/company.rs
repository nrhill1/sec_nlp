use serde_json::{Map, Value};

use super::util::{get_str, value_to_string};

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

pub(crate) fn extract_company_name(source: &Map<String, Value>) -> String {
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

fn is_insider_form(form_type: &str) -> bool {
    INSIDER_FORMS.contains(&form_type)
}
