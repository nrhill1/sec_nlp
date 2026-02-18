use crate::dictionary::DictionaryMatcher;
use crate::error::EntityError;
use crate::events;
use crate::models::{Entity, EventMention};
use crate::patterns;

#[derive(Debug)]
pub struct CoreEntityTagger {
    dictionary: Option<DictionaryMatcher>,
}

impl CoreEntityTagger {
    pub fn new(dictionary_path: Option<&str>) -> Result<Self, EntityError> {
        let dictionary = match dictionary_path {
            Some(path) if !path.trim().is_empty() => {
                Some(DictionaryMatcher::from_path(path.trim())?)
            }
            _ => None,
        };
        Ok(Self { dictionary })
    }

    pub fn tag_text(&self, text: &str) -> Vec<Entity> {
        let mut entities: Vec<Entity> = Vec::new();

        entities.extend(patterns::regulation::extract(text));
        entities.extend(patterns::money::extract(text));
        entities.extend(patterns::date::extract(text));
        entities.extend(patterns::person::extract(text));
        entities.extend(patterns::security_id::extract(text));

        if let Some(dictionary) = &self.dictionary {
            entities.extend(dictionary.find_entities(text));
        }

        entities.sort_by_key(|entity| {
            (
                entity.start,
                entity.end,
                entity.entity_type.clone(),
                entity.text.clone(),
            )
        });
        entities.dedup_by(|left, right| left.key() == right.key());
        entities
    }

    pub fn detect_events(&self, text: &str) -> Vec<EventMention> {
        events::detect_events(text)
    }

    pub fn tag_and_detect(&self, text: &str) -> (Vec<Entity>, Vec<EventMention>) {
        (self.tag_text(text), self.detect_events(text))
    }
}
