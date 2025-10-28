//! JSON document parsing

use super::document::{Document, DocumentFormat};
use crate::errors::{Error, Result};

/// Parse JSON SEC document
///
/// Extracts form type and metadata from JSON content.
///
/// # Examples
///
/// ```
/// use sec_o3::parse::parse_json;
///
/// let json = r#"{"submissionType":"8-K"}"#;
/// let doc = parse_json(json).unwrap();
/// assert_eq!(doc.form_type, "8-K");
/// ```
pub fn parse_json(json: &str) -> Result<Document> {
    let value: serde_json::Value =
        serde_json::from_str(json).map_err(|e| Error::Custom(format!("JSON parse error: {}", e)))?;

    let form_type = value
        .get("submissionType")
        .and_then(|v| v.as_str())
        .ok_or_else(|| Error::Custom("Missing submissionType in JSON".into()))?
        .to_string();

    let title = value.get("entityName").and_then(|v| v.as_str()).map(|s| s.to_string());

    let mut doc = Document::new(form_type, DocumentFormat::Json).with_size(json.len());

    if let Some(title) = title {
        doc = doc.with_title(title);
    }

    Ok(doc)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_json_basic() {
        let json = r#"{"submissionType":"8-K"}"#;
        let doc = parse_json(json).unwrap();
        assert_eq!(doc.form_type, "8-K");
    }

    #[test]
    fn test_parse_json_with_entity() {
        let json = r#"{"submissionType":"10-K","entityName":"Test Corp"}"#;
        let doc = parse_json(json).unwrap();
        assert_eq!(doc.form_type, "10-K");
        assert_eq!(doc.title.unwrap(), "Test Corp");
    }
}
