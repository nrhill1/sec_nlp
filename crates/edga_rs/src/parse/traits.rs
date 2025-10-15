// ============================================================================
// src/parse/traits.rs - Parser traits and data formats
// ============================================================================
use crate::errors::{ParserError, ValidationError};
use crate::filings::SecFormType;

/// Structural/encoding format of the input data (not the SEC form type).
#[derive(Debug, Copy, Clone, PartialEq, Eq, Hash)]
pub enum DataFormat {
    Html,
    Json,
    Xbrl,
}

impl std::fmt::Display for DataFormat {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            DataFormat::Html => "html",
            DataFormat::Json => "json",
            DataFormat::Xbrl => "xbrl",
        };
        f.write_str(s)
    }
}

impl std::str::FromStr for DataFormat {
    type Err = ValidationError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.trim().to_lowercase().as_str() {
            "html" => Ok(DataFormat::Html),
            "json" => Ok(DataFormat::Json),
            "xbrl" | "xml" => Ok(DataFormat::Xbrl),
            other => Err(ValidationError::UnknownFormat(other.to_string())),
        }
    }
}

/// Normalized representation of a parsed filing document.
#[derive(Debug, Clone)]
pub struct ParsedDocument {
    /// SEC filing form type (e.g., 10-K, 8-K, DEF 14A).
    pub form_type: SecFormType,
    /// Structural format of the parsed content.
    pub format: DataFormat,
    /// Optional title extracted from the content/metadata.
    pub title: Option<String>,
    /// Size in bytes of the input payload.
    pub bytes: usize,
}

/// Trait for parsing raw input into a `ParsedDocument`.
pub trait DocumentParser {
    fn parse(&self, input: &str) -> Result<ParsedDocument, ParserError>;
}
