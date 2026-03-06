use once_cell::sync::Lazy;
use regex::Regex;

use crate::models::{Entity, EntityType};

static ISO_DATE_PATTERN: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\b").expect("valid regex")
});
static US_DATE_PATTERN: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})\b").expect("valid regex")
});
static FISCAL_YEAR_PATTERN: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?i)\b(?:fiscal\s+year\s+|FY\s*)(?P<year>\d{4})\b").expect("valid regex")
});

pub fn extract(text: &str) -> Vec<Entity> {
    let mut entities: Vec<Entity> = Vec::new();

    for captures in ISO_DATE_PATTERN.captures_iter(text) {
        if let Some(entity) = entity_from_date_capture(text, &captures, true) {
            entities.push(entity);
        }
    }

    for captures in US_DATE_PATTERN.captures_iter(text) {
        if let Some(entity) = entity_from_date_capture(text, &captures, false) {
            entities.push(entity);
        }
    }

    for captures in FISCAL_YEAR_PATTERN.captures_iter(text) {
        let Some(matched) = captures.get(0) else {
            continue;
        };
        let Some(year_match) = captures.name("year") else {
            continue;
        };
        let normalized = format!("{}-12-31", year_match.as_str());
        entities.push(Entity::from_type(
            EntityType::Date,
            matched.as_str(),
            matched.start(),
            matched.end(),
            Some(normalized),
        ));
    }

    entities.sort_by_key(|entity| (entity.start, entity.end, entity.text.clone()));
    entities.dedup_by(|left, right| left.key() == right.key());
    entities
}

fn entity_from_date_capture(
    text: &str,
    captures: &regex::Captures<'_>,
    iso_style: bool,
) -> Option<Entity> {
    let matched = captures.get(0)?;
    let year = captures.name("year")?.as_str().parse::<u32>().ok()?;
    let month = captures.name("month")?.as_str().parse::<u32>().ok()?;
    let day = captures.name("day")?.as_str().parse::<u32>().ok()?;

    if !(1..=12).contains(&month) || !(1..=31).contains(&day) {
        return None;
    }

    let _ = iso_style;
    let normalized = format!("{year:04}-{month:02}-{day:02}");

    Some(Entity::from_type(
        EntityType::Date,
        &text[matched.start()..matched.end()],
        matched.start(),
        matched.end(),
        Some(normalized),
    ))
}
