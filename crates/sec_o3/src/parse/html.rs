//! HTML document parsing

use super::document::Document;
use crate::errors::Result;

/// Parse HTML SEC document
///
/// Extracts form type and metadata from HTML content.
///
/// # Examples
///
/// ```
/// use sec_o3::parse::parse_html;
///
/// let html = "<html><body>FORM 10-K</body></html>";
/// let doc = parse_html(html).unwrap();
/// assert_eq!(doc.form_type, "10-K");
/// ```
pub fn parse_html(_html: &str) -> Result<Document> {
    // For now, basic form type extraction

    todo!()

    // Ok(Document::new(form_type, DocumentFormat::Html).with_size(html.len()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_html_basic() {
        let html = "<html><body>FORM 10-K</body></html>";
        let doc = parse_html(html).unwrap();
        assert_eq!(doc.form_type, "10-K");
    }
}
