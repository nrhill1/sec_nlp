use once_cell::sync::Lazy;
use regex::Regex;

use crate::models::{Entity, EntityType};

static CUSIP_PATTERN: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"\b[0-9A-Z]{9}\b").expect("valid regex"));
static ISIN_PATTERN: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"\b[A-Z]{2}[0-9A-Z]{9}[0-9]\b").expect("valid regex"));

pub fn extract(text: &str) -> Vec<Entity> {
    let mut entities: Vec<Entity> = Vec::new();

    for m in CUSIP_PATTERN.find_iter(text) {
        let candidate = m.as_str();
        if !is_valid_cusip(candidate) {
            continue;
        }
        entities.push(Entity::from_type(
            EntityType::Cusip,
            candidate,
            m.start(),
            m.end(),
            Some(candidate.to_string()),
        ));
    }

    for m in ISIN_PATTERN.find_iter(text) {
        let candidate = m.as_str();
        if !is_valid_isin(candidate) {
            continue;
        }
        entities.push(Entity::from_type(
            EntityType::Isin,
            candidate,
            m.start(),
            m.end(),
            Some(candidate.to_string()),
        ));
    }

    entities.sort_by_key(|entity| (entity.start, entity.end, entity.text.clone()));
    entities.dedup_by(|left, right| left.key() == right.key());
    entities
}

fn is_valid_cusip(value: &str) -> bool {
    if value.len() != 9 {
        return false;
    }

    let chars: Vec<char> = value.chars().collect();
    let check_digit = chars[8].to_digit(10);
    let Some(expected_digit) = check_digit else {
        return false;
    };

    let mut sum: u32 = 0;
    for (index, c) in chars[..8].iter().enumerate() {
        let mut num = match *c {
            '0'..='9' => c.to_digit(10).unwrap_or(0),
            'A'..='Z' => (*c as u32) - ('A' as u32) + 10,
            '*' => 36,
            '@' => 37,
            '#' => 38,
            _ => return false,
        };

        if index % 2 == 1 {
            num *= 2;
        }

        sum += (num / 10) + (num % 10);
    }

    let computed_digit = (10 - (sum % 10)) % 10;
    computed_digit == expected_digit
}

fn is_valid_isin(value: &str) -> bool {
    if value.len() != 12 {
        return false;
    }

    let mut expanded = String::new();
    for c in value.chars() {
        if c.is_ascii_digit() {
            expanded.push(c);
        } else if c.is_ascii_uppercase() {
            expanded.push_str(&((c as u32) - ('A' as u32) + 10).to_string());
        } else {
            return false;
        }
    }

    let mut sum: u32 = 0;
    let mut double = false;
    for digit_char in expanded.chars().rev() {
        let Some(mut digit) = digit_char.to_digit(10) else {
            return false;
        };
        if double {
            digit *= 2;
            if digit > 9 {
                digit -= 9;
            }
        }
        sum += digit;
        double = !double;
    }

    sum % 10 == 0
}

#[cfg(test)]
mod tests {
    use super::{is_valid_cusip, is_valid_isin};

    #[test]
    fn validates_known_identifiers() {
        assert!(is_valid_cusip("037833100"));
        assert!(is_valid_isin("US0378331005"));
    }
}
