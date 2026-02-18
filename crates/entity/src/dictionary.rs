use std::fs::File;
use std::io::{BufRead, BufReader};

use aho_corasick::AhoCorasickBuilder;
use serde::Deserialize;

use crate::error::EntityError;
use crate::models::{Entity, EntityType};

#[derive(Debug, Clone, Deserialize)]
struct CompanyRecord {
    name: String,
    ticker: Option<String>,
    cik: Option<String>,
}

#[derive(Debug)]
pub struct DictionaryMatcher {
    automaton: aho_corasick::AhoCorasick,
    records: Vec<CompanyRecord>,
}

impl DictionaryMatcher {
    pub fn from_path(path: &str) -> Result<Self, EntityError> {
        let file = File::open(path)?;
        let reader = BufReader::new(file);

        let mut records: Vec<CompanyRecord> = Vec::new();
        let mut patterns: Vec<String> = Vec::new();

        for line_result in reader.lines() {
            let line = line_result?;
            let trimmed = line.trim();
            if trimmed.is_empty() {
                continue;
            }
            let record: CompanyRecord = serde_json::from_str(trimmed)?;
            if record.name.trim().is_empty() {
                continue;
            }
            patterns.push(record.name.clone());
            records.push(record);
        }

        if patterns.is_empty() {
            return Err(EntityError::new("dictionary contains no company names"));
        }

        let automaton = AhoCorasickBuilder::new()
            .ascii_case_insensitive(true)
            .build(patterns)
            .map_err(|err| EntityError::new(err.to_string()))?;

        Ok(Self { automaton, records })
    }

    pub fn find_entities(&self, text: &str) -> Vec<Entity> {
        let mut entities: Vec<Entity> = Vec::new();

        for m in self.automaton.find_iter(text) {
            let Some(record) = self.records.get(m.pattern().as_usize()) else {
                continue;
            };
            let normalized = Some(record.name.clone());
            let mut surface = text[m.start()..m.end()].to_string();
            if let Some(ticker) = record.ticker.as_deref() {
                surface.push_str(&format!(" ({ticker})"));
            }
            if let Some(cik) = record.cik.as_deref() {
                surface.push_str(&format!(" [CIK {cik}]"));
            }
            entities.push(Entity::from_type(
                EntityType::Org,
                surface,
                m.start(),
                m.end(),
                normalized,
            ));
        }

        entities.sort_by_key(|entity| (entity.start, entity.end, entity.text.clone()));
        entities.dedup_by(|left, right| left.key() == right.key());
        entities
    }
}
