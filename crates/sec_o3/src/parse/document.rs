//! Document types and metadata

use serde::{Deserialize, Serialize};

/// Document format type
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum DocumentFormat {
    Html,
    Json,
    Xml,
    Text,
}

/// Parsed document metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Document {
    /// SEC form type (e.g., "10-K", "8-K")
    pub form_type: String,
    /// Document format
    pub format: DocumentFormat,
    /// Document title if available
    pub title: Option<String>,
    /// Document size in bytes
    pub size_bytes: usize,
}

impl Document {
    /// Create a new document
    pub fn new(form_type: impl Into<String>, format: DocumentFormat) -> Self {
        Self {
            form_type: form_type.into(),
            format,
            title: None,
            size_bytes: 0,
        }
    }

    /// Set document title
    pub fn with_title(mut self, title: impl Into<String>) -> Self {
        self.title = Some(title.into());
        self
    }

    /// Set document size
    pub fn with_size(mut self, size: usize) -> Self {
        self.size_bytes = size;
        self
    }
}
