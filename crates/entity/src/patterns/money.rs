use once_cell::sync::Lazy;
use regex::Regex;

use crate::models::{Entity, EntityType};

static MONEY_PATTERN: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r"(?ix)
        (
            (?:USD\s*)?\$\s*(?P<dollar_num>-?\d[\d,]*(?:\.\d+)?)\s*(?P<dollar_unit>thousand|million|billion|k|m|b)?
            |
            USD\s*(?P<usd_num>-?\d[\d,]*(?:\.\d+)?)\s*(?P<usd_unit>thousand|million|billion|k|m|b)?
            |
            (?P<plain_num>-?\d[\d,]*(?:\.\d+)?)\s*(?P<plain_unit>thousand|million|billion|k|m|b)
        )",
    )
    .expect("valid money regex")
});

pub fn extract(text: &str) -> Vec<Entity> {
    let mut entities: Vec<Entity> = Vec::new();

    for captures in MONEY_PATTERN.captures_iter(text) {
        let Some(matched) = captures.get(0) else {
            continue;
        };

        let (raw_number, raw_unit) = if let Some(number_match) = captures.name("dollar_num") {
            (
                number_match.as_str(),
                captures
                    .name("dollar_unit")
                    .map(|m| m.as_str())
                    .unwrap_or(""),
            )
        } else if let Some(number_match) = captures.name("usd_num") {
            (
                number_match.as_str(),
                captures
                    .name("usd_unit")
                    .map(|m| m.as_str())
                    .unwrap_or(""),
            )
        } else if let Some(number_match) = captures.name("plain_num") {
            (
                number_match.as_str(),
                captures
                    .name("plain_unit")
                    .map(|m| m.as_str())
                    .unwrap_or(""),
            )
        } else {
            continue;
        };

        let normalized = normalize_amount(raw_number, raw_unit).map(|value| format!("{value:.2}"));

        entities.push(Entity::from_type(
            EntityType::Money,
            matched.as_str().trim(),
            matched.start(),
            matched.end(),
            normalized,
        ));
    }

    entities
}

fn normalize_amount(raw_number: &str, raw_unit: &str) -> Option<f64> {
    let cleaned = raw_number.replace(',', "");
    let value = cleaned.parse::<f64>().ok()?;
    let multiplier = match raw_unit.to_ascii_lowercase().as_str() {
        "thousand" | "k" => 1_000.0,
        "million" | "m" => 1_000_000.0,
        "billion" | "b" => 1_000_000_000.0,
        _ => 1.0,
    };
    Some(value * multiplier)
}
