use once_cell::sync::Lazy;
use regex::Regex;

use crate::models::{Entity, EntityType};

static TITLED_PERSON_PATTERN: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"\b(?:Mr|Ms|Mrs|Dr)\.\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b").expect("valid regex")
});

static OFFICER_PERSON_PATTERN: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r"\b[A-Z][a-z]+\s+[A-Z][a-z]+,\s*(?:CEO|CFO|President|Director|Chairman|Chairwoman)\b",
    )
    .expect("valid regex")
});

pub fn extract(text: &str) -> Vec<Entity> {
    let mut entities: Vec<Entity> = Vec::new();

    for pattern in [&*TITLED_PERSON_PATTERN, &*OFFICER_PERSON_PATTERN] {
        for m in pattern.find_iter(text) {
            entities.push(Entity::from_type(
                EntityType::Person,
                m.as_str(),
                m.start(),
                m.end(),
                None,
            ));
        }
    }

    entities.sort_by_key(|entity| (entity.start, entity.end, entity.text.clone()));
    entities.dedup_by(|left, right| left.key() == right.key());
    entities
}
