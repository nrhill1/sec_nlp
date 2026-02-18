use once_cell::sync::Lazy;
use regex::Regex;

use crate::models::{Entity, EntityType};

static RULE_PATTERN: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(?i)\bRule\s+\d+[A-Za-z]?(?:-\d+)?\b").expect("valid regex"));
static SECTION_PATTERN: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r"(?i)\bSection\s+\d+[A-Za-z]?\([a-z0-9]+\)|\bSection\s+\d+[A-Za-z]?\b",
    )
    .expect("valid regex")
});
static REGULATION_PATTERN: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(?i)\bRegulation\s+[A-Z](?:-[A-Z])?\b").expect("valid regex"));
static ITEM_PATTERN: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(?i)\bItem\s+\d+[A-Z]?\b").expect("valid regex"));

pub fn extract(text: &str) -> Vec<Entity> {
    let mut entities: Vec<Entity> = Vec::new();
    for pattern in [
        &*RULE_PATTERN,
        &*SECTION_PATTERN,
        &*REGULATION_PATTERN,
        &*ITEM_PATTERN,
    ] {
        for m in pattern.find_iter(text) {
            let matched = m.as_str().trim();
            entities.push(Entity::from_type(
                EntityType::Regulation,
                matched,
                m.start(),
                m.end(),
                Some(matched.to_string()),
            ));
        }
    }
    entities.sort_by_key(|entity| (entity.start, entity.end, entity.text.clone()));
    entities.dedup_by(|left, right| left.key() == right.key());
    entities
}
