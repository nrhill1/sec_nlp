use pyo3::prelude::*;
use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum EntityType {
    Org,
    Person,
    Money,
    Date,
    Regulation,
    Cusip,
    Isin,
}

impl EntityType {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Org => "ORG",
            Self::Person => "PERSON",
            Self::Money => "MONEY",
            Self::Date => "DATE",
            Self::Regulation => "REGULATION",
            Self::Cusip => "CUSIP",
            Self::Isin => "ISIN",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Span {
    pub start: usize,
    pub end: usize,
}

#[derive(Debug, Clone, Serialize)]
#[pyclass]
pub struct Entity {
    #[pyo3(get)]
    pub entity_type: String,
    #[pyo3(get)]
    pub text: String,
    #[pyo3(get)]
    pub start: usize,
    #[pyo3(get)]
    pub end: usize,
    #[pyo3(get)]
    pub normalized: Option<String>,
}

#[pymethods]
impl Entity {
    #[new]
    #[pyo3(signature = (entity_type, text, start, end, normalized=None))]
    fn new(
        entity_type: String,
        text: String,
        start: usize,
        end: usize,
        normalized: Option<String>,
    ) -> Self {
        Self {
            entity_type,
            text,
            start,
            end,
            normalized,
        }
    }
}

impl Entity {
    pub fn from_type(
        entity_type: EntityType,
        text: impl Into<String>,
        start: usize,
        end: usize,
        normalized: Option<String>,
    ) -> Self {
        Self {
            entity_type: entity_type.as_str().to_string(),
            text: text.into(),
            start,
            end,
            normalized,
        }
    }

    pub fn key(&self) -> (&str, usize, usize, &str, Option<&str>) {
        (
            self.entity_type.as_str(),
            self.start,
            self.end,
            self.text.as_str(),
            self.normalized.as_deref(),
        )
    }
}

#[derive(Debug, Clone, Serialize)]
#[pyclass]
pub struct EventMention {
    #[pyo3(get)]
    pub event_type: String,
    #[pyo3(get)]
    pub text: String,
    #[pyo3(get)]
    pub start: usize,
    #[pyo3(get)]
    pub end: usize,
    #[pyo3(get)]
    pub confidence: f64,
}

#[pymethods]
impl EventMention {
    #[new]
    fn new(event_type: String, text: String, start: usize, end: usize, confidence: f64) -> Self {
        Self {
            event_type,
            text,
            start,
            end,
            confidence,
        }
    }
}

impl EventMention {
    pub fn key(&self) -> (&str, usize, usize, &str) {
        (
            self.event_type.as_str(),
            self.start,
            self.end,
            self.text.as_str(),
        )
    }
}
