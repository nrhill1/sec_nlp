//! Form type inference utilities (regex-free matching).
//!
//! Strategy:
//! 1) Scan only a small prefix of the document for speed (most signals occur early).
//! 2) Try explicit header/JSON *labels* (e.g., `CONFORMED SUBMISSION TYPE`, `"submissionType"`)
//!    and parse the next token with simple string operations.
//! 3) If no label match, run a single-pass **Aho–Corasick** literal search over a curated list
//!    of canonical SEC form strings (and common aliases). This avoids heavyweight regex and
//!    remains easy to maintain.
//!
//! **Note:** per project choice, this module intentionally **does not infer Forms 3/4/5**.
//! If you ever want them back, add them to `LITERALS`.

use crate::filings::FormType;
use aho_corasick::{AhoCorasick, AhoCorasickBuilder, MatchKind};
use once_cell::sync::Lazy;
use std::{borrow::Cow, str::FromStr};

/// Return up to a 64 KiB prefix for faster scanning.
/// Most useful signals occur in headers or the beginning of the document.
fn head(s: &str) -> &str {
    const CAP: usize = 64 * 1024;
    if s.len() > CAP {
        &s[..CAP]
    } else {
        s
    }
}

/// Common header/JSON keys that may precede the filing type.
static LABELS: &[&str] = &[
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
];

/// Literal forms (canonical + popular aliases).
/// Keep ordering stable — the Aho–Corasick pattern index maps back into this table.
///
/// **No 3/4/5 here by design.**
#[rustfmt::skip]
static LITERALS: &[(&str, FormType)] = &[
    // Periodic
    ("10-K",   FormType::TenK),   ("10K",    FormType::TenK),
    ("10-K/A", FormType::TenKA),  ("10K/A",  FormType::TenKA),
    ("10-Q",   FormType::TenQ),   ("10Q",    FormType::TenQ),
    ("10-Q/A", FormType::TenQA),  ("10Q/A",  FormType::TenQA),

    // Current
    ("8-K",    FormType::EightK), ("8K",     FormType::EightK),
    ("8-K/A",  FormType::EightKA),("8K/A",   FormType::EightKA),

    // Proxy
    ("DEF 14A",  FormType::Def14A), ("DEF14A",  FormType::Def14A),
    ("DEF 14C",  FormType::Def14C), ("DEF14C",  FormType::Def14C),
    ("DEFM14A",  FormType::DefM14A),("DEFM14A/A", FormType::DefM14AA),
    ("DEFC14A",  FormType::DefC14A),("DEFC14A/A", FormType::DefC14AA),
    ("DEFC14C",  FormType::DefC14C),("DEFC14C/A", FormType::DefC14CA),

    // Registration Statements - S series
    ("S-1",   FormType::S1),   ("S1",   FormType::S1),
    ("S-1/A", FormType::S1A),  ("S1/A", FormType::S1A),
    ("S-3",   FormType::S3),   ("S3",   FormType::S3),
    ("S-3/A", FormType::S3A),  ("S3/A", FormType::S3A),
    ("S-4",   FormType::S4),   ("S4",   FormType::S4),
    ("S-4/A", FormType::S4A),  ("S4/A", FormType::S4A),
    ("S-8",   FormType::S8),   ("S8",   FormType::S8),
    ("S-8/A", FormType::S8A),  ("S8/A", FormType::S8A),
    ("S-11",  FormType::S11),  ("S11",  FormType::S11),
    ("S-11/A",FormType::S11A), ("S11/A",FormType::S11A),

    // Foreign Private Issuers
    ("20-F",   FormType::TwentyF),  ("20F",   FormType::TwentyF),
    ("20-F/A", FormType::TwentyFA), ("20F/A", FormType::TwentyFA),
    ("6-K",    FormType::SixK),     ("6K",    FormType::SixK),
    ("6-K/A",  FormType::SixKA),    ("6K/A",  FormType::SixKA),

    // Employee Benefit Plans
    ("11-K",   FormType::ElevenK),  ("11K",   FormType::ElevenK),
    ("11-K/A", FormType::ElevenKA), ("11K/A", FormType::ElevenKA),

    // Institutional Investment Managers
    ("13F-HR",   FormType::ThirteenFHr),   ("13FHR",   FormType::ThirteenFHr),
    ("13F-HR/A", FormType::ThirteenFHrA),  ("13FHR/A", FormType::ThirteenFHrA),
    ("13F-NT",   FormType::ThirteenFNT),
    ("13F-NT/A", FormType::ThirteenFNTA),

    // Beneficial Ownership
    ("SC 13D",   FormType::Sc13D),   ("SC13D",   FormType::Sc13D),
    ("SC 13D/A", FormType::Sc13DA),  ("SC13D/A", FormType::Sc13DA),
    ("SC 13G",   FormType::Sc13G),   ("SC13G",   FormType::Sc13G),
    ("SC 13G/A", FormType::Sc13GA),  ("SC13G/A", FormType::Sc13GA),

    // Offerings & Prospectuses
    ("424B5",   FormType::FourTwoFourB5),
    ("425",     FormType::FourTwoFive),
    ("POS EX",  FormType::PosEx),
    ("POS 462B",FormType::Pos462B),
    ("POS 462C",FormType::Pos462C),
    ("POS ASR", FormType::PosAsr),

    // Exempt Offerings
    ("144",     FormType::OneFortyFour), ("144/A", FormType::OneFortyFourA),
    ("D",       FormType::FormD),

    // Notifications
    ("NT 10-K",   FormType::NT10K),   ("NT 10-K/A", FormType::NT10KA),
    ("NT 10-Q",   FormType::NT10Q),   ("NT 10-Q/A", FormType::NT10QA),
    ("NT 11-K",   FormType::NT11K),
    ("NT 15D2",   FormType::NT15D2),

    // Other
    ("40-F",      FormType::FortyF),     ("40F",      FormType::FortyF),
    ("40-F/A",    FormType::FortyFA),    ("40F/A",    FormType::FortyFA),
    ("40-FR12B",  FormType::FortyFR12B), ("40FR12B",  FormType::FortyFR12B),
    ("40-FR12B/A",FormType::FortyFR12BA),("40FR12BA", FormType::FortyFR12BA),
    ("40-FR12G",  FormType::FortyFR12G), ("40FR12G",  FormType::FortyFR12G),
    ("40-FR12G/A",FormType::FortyFR12GA),("40FR12GA", FormType::FortyFR12GA),

    ("25",        FormType::TwentyFive), ("25/A",     FormType::TwentyFiveA),
    ("RW",        FormType::Rw),         ("RW/WD",    FormType::RwWd), ("RW/Wd", FormType::RwWd),
];

/// Aho–Corasick automaton over the literal patterns (case-insensitive).
static AC: Lazy<AhoCorasick> = Lazy::new(|| {
    let pats: Vec<&str> = LITERALS.iter().map(|(s, _)| *s).collect();
    AhoCorasickBuilder::new()
        .match_kind(MatchKind::LeftmostFirst)
        .ascii_case_insensitive(true)
        .build(pats)
        .expect("failed to build AhoCorasick automaton")
});

/// Infer a [`FormType`] from the input without regex.
///
/// 1) Check explicit labels (header/JSON).
/// 2) Single-pass Aho–Corasick literal search (case-insensitive).
pub fn infer_form_type(input: &str) -> Option<FormType> {
    let s = head(input);

    // 1) Labeled headers/JSON first — most reliable/cheap.
    for &key in LABELS {
        if let Some(val) = extract_after_label(s, key) {
            if let Some(ft) = form_from_token(&val) {
                return Some(ft);
            }
        }
    }

    // 2) Literal search — maps pattern ID back to the same index in `LITERALS`.
    if let Some(m) = AC.find(s) {
        return Some(LITERALS[m.pattern()].1);
    }

    None
}

/// Extract the first token that appears after a label (e.g., `LABEL: value`, `"label":"value"`).
fn extract_after_label(hay: &str, label: &str) -> Option<String> {
    let lab_lower = label.to_ascii_lowercase();
    let hay_lower = hay.to_ascii_lowercase();
    let idx = hay_lower.find(&lab_lower)?;
    let tail = &hay[idx + label.len()..];

    // Find a common separator, then peel a clean token from that line.
    for sep in [":", "\"", " "] {
        if let Some(pos) = tail.find(sep) {
            let after = &tail[pos + 1..];
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

/// Normalize a token (e.g., `10K`, `SC13D`, `DEF 14A`) into a canonical-ish string.
///
/// Returns a [`Cow`] to avoid allocating when no changes are needed.
///
/// - Uppercases & trims
/// - Strips optional `"FORM"` prefix
/// - Removes internal whitespace
/// - Canonicalizes `10K→10-K`, `10Q→10-Q`, `8K→8-K`, `SC13D→SC 13D`, `SC13G→SC 13G`
fn normalize_token(tok: &str) -> Cow<'_, str> {
    let upper = tok.trim().to_ascii_uppercase();
    // Strip "FORM" prefix if present (common in prose snippets).
    let joined = upper
        .split_whitespace()
        .skip_while(|part| *part == "FORM")
        .collect::<Vec<_>>()
        .join(" ");
    let compact: String = joined.chars().filter(|c| !c.is_whitespace()).collect();

    match compact.as_str() {
        "10K" => Cow::Borrowed("10-K"),
        "10Q" => Cow::Borrowed("10-Q"),
        "8K" => Cow::Borrowed("8-K"),
        "SC13D" => Cow::Borrowed("SC 13D"),
        "SC13G" => Cow::Borrowed("SC 13G"),
        _ => {
            if compact == tok {
                Cow::Borrowed(tok)
            } else {
                Cow::Owned(compact)
            }
        }
    }
}

/// Map a token (from header/JSON) to a [`FormType`], using normalization and the literal table.
fn form_from_token(tok: &str) -> Option<FormType> {
    let norm = normalize_token(tok);

    // First, try the enum's FromStr (covers most canonical cases).
    if let Ok(ft) = FormType::from_str(norm.as_ref()) {
        return Some(ft);
    }

    // Fallback: compare with our literals in a case-insensitive way.
    let up = norm.to_ascii_uppercase();
    for &(lit, ft) in LITERALS {
        if lit.eq_ignore_ascii_case(&up) {
            return Some(ft);
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::filings::FormType;

    #[test]
    fn header_json_detection() {
        let s = r#"
<SEC-HEADER>
CONFORMED SUBMISSION TYPE: 10-K
</SEC-HEADER>
{"submissionType":"8-K"}
        "#;
        // First detected wins (10-K comes earlier in the prefix).
        assert_eq!(infer_form_type(s), Some(FormType::TenK));
        // Token path:
        assert_eq!(form_from_token("DEF 14A"), Some(FormType::Def14A));
        assert_eq!(form_from_token("sc13d"), Some(FormType::Sc13D));
    }

    #[test]
    fn literal_detection() {
        let s = "Some prose… This is a DEF 14A related document";
        assert_eq!(infer_form_type(s), Some(FormType::Def14A));

        let s2 = "Prospectus supplement filed pursuant to Rule 424B5";
        assert_eq!(infer_form_type(s2), Some(FormType::FourTwoFourB5));
    }

    #[test]
    fn normalizer() {
        assert_eq!(normalize_token("  10k ").as_ref(), "10-K");
        assert_eq!(normalize_token("FORM 10-Q").as_ref(), "10-Q");
        assert_eq!(normalize_token("SC13D").as_ref(), "SC 13D");
        // Compacts whitespace:
        assert_eq!(normalize_token("DEF 14A").as_ref(), "DEF14A");
    }
}
