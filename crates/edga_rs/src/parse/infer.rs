// src/parse/infer.rs
use crate::filings::SecFormType;
use once_cell::sync::Lazy;
use regex::Regex;
use std::str::FromStr;

/// Scan a small prefix for speed; most signals occur early.
fn head(s: &str) -> &str {
    const CAP: usize = 64 * 1024; // 64 KiB
    if s.len() > CAP {
        &s[..CAP]
    } else {
        s
    }
}

/// Try a direct parse first, then regex extraction, then "Form XX" style.
pub fn infer_form_type(input: &str) -> Option<SecFormType> {
    let s = head(input);

    // 1) Explicit EDGAR field labels commonly found in headers or JSON exports
    // e.g., "CONFORMED SUBMISSION TYPE: 10-K" or JSON: {"submissionType":"10-K"}
    for key in [
        "CONFORMED SUBMISSION TYPE",
        "CONFORMED-SUBMISSION-TYPE",
        "SUBMISSION TYPE",
        "SUBMISSION-TYPE",
        "FORM TYPE",
        "FORM-TYPE",
        "\"submissionType\"",
        "\"conformedSubmissionType\"",
        "\"formType\"",
        "\"form_type\"",
        "\"form\"",
        "\"type\"",
    ] {
        if let Some(val) = extract_after_label(s, key) {
            if let Ok(ft) = SecFormType::from_str(&val) {
                return Some(ft);
            }
        }
    }

    // 2) Direct token regex (handles aliases like SC13D/SC 13D, 10Q/10-Q)
    static TOK_RE: Lazy<Regex> = Lazy::new(|| {
        Regex::new(
            r"(?ix)
            \b(
                10-K | 10Q | 10\-Q | 8-K | DEF \s* 14A |
                S\-1 | S\-3 | S\-4 | S\-8 |
                20\-F | 6\-K | 11\-K |
                13F\-HR | 144 | SC \s*13D | SC \s*13G |
                424B5 | 425
            )\b", //TODO: Add support for forms 3/4/5
        )
        .unwrap()
    });

    if let Some(m) = TOK_RE.captures(s).and_then(|c| c.get(1)) {
        if let Ok(ft) = SecFormType::from_str(m.as_str()) {
            return Some(ft);
        }
    }

    // 3) "Form 10-K" / "FORM 8-K" pattern
    static FORM_WORD_RE: Lazy<Regex> =
        Lazy::new(|| Regex::new(r"(?i)\bFORM\s+([A-Z0-9\- ]{2,8})\b").unwrap());
    if let Some(m) = FORM_WORD_RE.captures(s).and_then(|c| c.get(1)) {
        if let Ok(ft) = SecFormType::from_str(m.as_str()) {
            return Some(ft);
        }
    }

    None
}

/// Extract a value that appears after a label (e.g., `LABEL: value`, `"label":"value"`)
fn extract_after_label(hay: &str, label: &str) -> Option<String> {
    let lab = label.to_ascii_lowercase();
    let lh = hay.to_ascii_lowercase();
    let idx = lh.find(&lab)?;
    let tail = &hay[idx + label.len()..];

    // Simple split on JSON, colon, or whitespace after label.
    // Examples:
    //   LABEL: 10-K
    //   "label":"10-K"
    //   label 10-K
    for sep in [":", "\"", " "] {
        if let Some(pos) = tail.find(sep) {
            let after = &tail[pos + 1..];
            // Take up to first delimiter/end of line
            let token = after
                .lines()
                .next()
                .unwrap_or("")
                .trim_matches(|c: char| c.is_whitespace() || c == '"' || c == ',')
                .split_whitespace()
                .next()
                .unwrap_or("")
                .to_string();
            if !token.is_empty() {
                return Some(token);
            }
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::filings::SecFormType;

    #[test]
    fn test_infer_from_conformed_header() {
        let input = r#"
<SEC-DOCUMENT>
<SEC-HEADER>
CONFORMED SUBMISSION TYPE: 10-K
PUBLIC DOCUMENT COUNT: 123
</SEC-HEADER>
        "#;
        assert_eq!(infer_form_type(input), Some(SecFormType::TenK));
    }

    #[test]
    fn test_infer_from_json() {
        let input = r#"{"submissionType":"8-K","cik":"0001234567"}"#;
        assert_eq!(infer_form_type(input), Some(SecFormType::EightK));
    }

    #[test]
    fn test_infer_from_form_keyword() {
        let input = "This is a FORM 10-Q filing for the quarter ending...";
        assert_eq!(infer_form_type(input), Some(SecFormType::TenQ));
    }

    #[test]
    fn test_infer_sc13d_variants() {
        assert_eq!(infer_form_type("SC 13D"), Some(SecFormType::Sc13D));
        assert_eq!(infer_form_type("SC13D"), Some(SecFormType::Sc13D));
    }

    #[test]
    fn test_infer_form_3_4_5() {
        assert_eq!(infer_form_type("FORM 3"), Some(SecFormType::Form3));
        assert_eq!(infer_form_type("FORM 4"), Some(SecFormType::Form4));
        assert_eq!(infer_form_type("FORM 5"), Some(SecFormType::Form5));
    }

    #[test]
    fn test_no_match() {
        assert_eq!(infer_form_type("random text with no form type"), None);
    }
}
