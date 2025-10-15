// src/parse/mod.rs
pub mod infer;
pub mod traits;

pub use traits::{DataFormat, DocumentParser, ParsedDocument};

use crate::errors::{ParseError, ParserError};
use crate::filings::SecFormType;
use scraper::{Html, Selector};

pub type Result<T> = std::result::Result<T, ParserError>;

#[derive(Debug, Default)]
pub struct HtmlParser;

#[derive(Debug, Default)]
pub struct JsonParser;

impl DocumentParser for HtmlParser {
    fn parse(&self, input: &str) -> Result<ParsedDocument> {
        let doc = Html::parse_document(input);
        let sel =
            Selector::parse("title").map_err(|e| ParserError::ParseDetail(ParseError::Selector(e.to_string())))?;

        let title = doc
            .select(&sel)
            .next()
            .map(|n| n.text().collect::<String>().trim().to_owned())
            .filter(|s| !s.is_empty());

        let form_type = infer::infer_form_type(input)
            .ok_or_else(|| ParserError::Parse("Could not determine form type from document".into()))?;

        Ok(ParsedDocument {
            form_type,
            format: DataFormat::Html,
            title,
            bytes: input.len(),
        })
    }
}

impl DocumentParser for JsonParser {
    fn parse(&self, input: &str) -> Result<ParsedDocument> {
        let v: serde_json::Value =
            serde_json::from_str(input).map_err(|e| ParserError::ParseDetail(ParseError::Json(e)))?;

        let title = v.get("title").and_then(|t| t.as_str()).map(str::to_string);

        // Try to infer form type from content
        let form_type = infer::infer_form_type(input).unwrap_or(SecFormType::TenQ); // Default fallback

        Ok(ParsedDocument {
            form_type,
            format: DataFormat::Json,
            title,
            bytes: input.len(),
        })
    }
}

pub fn parse(format: DataFormat, input: &str) -> Result<ParsedDocument> {
    match format {
        DataFormat::Html => HtmlParser.parse(input),
        DataFormat::Json => JsonParser.parse(input),
        DataFormat::Xbrl => Err(ParserError::NotImplemented("XBRL parsing not implemented".into())),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_html_with_title() {
        let html = r#"
<!DOCTYPE html>
<html>
<head><title>Test Filing</title></head>
<body>FORM 10-K content here</body>
</html>
        "#;
        let result = parse(DataFormat::Html, html).unwrap();
        assert_eq!(result.title, Some("Test Filing".to_string()));
        assert_eq!(result.format, DataFormat::Html);
        assert_eq!(result.form_type, SecFormType::TenK);
    }

    #[test]
    fn test_parse_json() {
        let json = r#"{"title":"Filing Document","submissionType":"8-K"}"#;
        let result = parse(DataFormat::Json, json).unwrap();
        assert_eq!(result.title, Some("Filing Document".to_string()));
        assert_eq!(result.format, DataFormat::Json);
        assert_eq!(result.form_type, SecFormType::EightK);
    }

    #[test]
    fn test_parse_xbrl_not_implemented() {
        let result = parse(DataFormat::Xbrl, "<xbrl>data</xbrl>");
        assert!(result.is_err());
        assert!(matches!(result.unwrap_err(), ParserError::NotImplemented(_)));
    }
}
