use std::collections::HashMap;

use crate::models::XbrlContext;
use once_cell::sync::Lazy;
use regex::Regex;

static CONTEXT_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r#"(?is)<(?:[A-Za-z_][\w\.-]*:)?context\b[^>]*\bid\s*=\s*["'](?P<id>[^"']+)["'][^>]*>(?P<body>.*?)</(?:[A-Za-z_][\w\.-]*:)?context>"#,
    )
    .unwrap()
});

static UNIT_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r#"(?is)<(?:[A-Za-z_][\w\.-]*:)?unit\b[^>]*\bid\s*=\s*["'](?P<id>[^"']+)["'][^>]*>(?P<body>.*?)</(?:[A-Za-z_][\w\.-]*:)?unit>"#,
    )
    .unwrap()
});

static IDENTIFIER_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r#"(?is)<(?:[A-Za-z_][\w\.-]*:)?identifier\b[^>]*>(?P<value>.*?)</(?:[A-Za-z_][\w\.-]*:)?identifier>"#,
    )
    .unwrap()
});

static START_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r#"(?is)<(?:[A-Za-z_][\w\.-]*:)?startDate\b[^>]*>(?P<value>.*?)</(?:[A-Za-z_][\w\.-]*:)?startDate>"#,
    )
    .unwrap()
});

static END_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r#"(?is)<(?:[A-Za-z_][\w\.-]*:)?endDate\b[^>]*>(?P<value>.*?)</(?:[A-Za-z_][\w\.-]*:)?endDate>"#,
    )
    .unwrap()
});

static INSTANT_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r#"(?is)<(?:[A-Za-z_][\w\.-]*:)?instant\b[^>]*>(?P<value>.*?)</(?:[A-Za-z_][\w\.-]*:)?instant>"#,
    )
    .unwrap()
});

static SEGMENT_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r#"(?is)<(?:[A-Za-z_][\w\.-]*:)?segment\b[^>]*>(?P<value>.*?)</(?:[A-Za-z_][\w\.-]*:)?segment>"#,
    )
    .unwrap()
});

static MEASURE_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r#"(?is)<(?:[A-Za-z_][\w\.-]*:)?measure\b[^>]*>(?P<value>.*?)</(?:[A-Za-z_][\w\.-]*:)?measure>"#,
    )
    .unwrap()
});

static TAG_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"(?is)<[^>]+>").unwrap());
static AS_OF_DATE_RE: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(?i)As_Of_(?P<m>\d{1,2})_(?P<d>\d{1,2})_(?P<y>\d{4})").unwrap());
static ISO_DATE_RE: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(?P<y>\d{4})[-_]?((?P<m>\d{2})[-_]?)(?P<d>\d{2})").unwrap());

fn clean_text(value: &str) -> String {
    let stripped = TAG_RE.replace_all(value, "");
    stripped
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .trim()
        .to_string()
}

fn extract_capture(regex: &Regex, text: &str) -> Option<String> {
    regex
        .captures(text)
        .and_then(|captures| captures.name("value"))
        .map(|m| clean_text(m.as_str()))
        .filter(|value| !value.is_empty())
}

pub fn parse_contexts(content: &str) -> HashMap<String, XbrlContext> {
    let mut contexts: HashMap<String, XbrlContext> = HashMap::new();
    for captures in CONTEXT_RE.captures_iter(content) {
        let id = captures
            .name("id")
            .map(|m| m.as_str().trim().to_string())
            .unwrap_or_default();
        if id.is_empty() {
            continue;
        }
        let body = captures
            .name("body")
            .map(|m| m.as_str())
            .unwrap_or_default();
        let context = XbrlContext {
            id: id.clone(),
            entity_id: extract_capture(&IDENTIFIER_RE, body),
            period_start: extract_capture(&START_RE, body),
            period_end: extract_capture(&END_RE, body),
            period_instant: extract_capture(&INSTANT_RE, body),
            segment: extract_capture(&SEGMENT_RE, body),
        };
        contexts.insert(id, context);
    }
    contexts
}

pub fn parse_units(content: &str) -> HashMap<String, String> {
    let mut units: HashMap<String, String> = HashMap::new();
    for captures in UNIT_RE.captures_iter(content) {
        let id = captures
            .name("id")
            .map(|m| m.as_str().trim().to_string())
            .unwrap_or_default();
        if id.is_empty() {
            continue;
        }
        let body = captures
            .name("body")
            .map(|m| m.as_str())
            .unwrap_or_default();
        if let Some(measure) = extract_capture(&MEASURE_RE, body) {
            units.insert(id, measure);
        }
    }
    units
}

pub fn infer_period_end_from_context(context_ref: &str) -> Option<String> {
    if let Some(captures) = AS_OF_DATE_RE.captures(context_ref) {
        let year = captures.name("y")?.as_str();
        let month = captures.name("m")?.as_str().parse::<u8>().ok()?;
        let day = captures.name("d")?.as_str().parse::<u8>().ok()?;
        return Some(format!("{}-{:02}-{:02}", year, month, day));
    }

    let captures = ISO_DATE_RE.captures(context_ref)?;
    let year = captures.name("y")?.as_str();
    let month = captures.name("m")?.as_str();
    let day = captures.name("d")?.as_str();
    Some(format!("{}-{}-{}", year, month, day))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_contexts_extracts_entity_and_period() {
        let xml = r#"
        <xbrli:context id="ctx_20241231">
          <xbrli:entity><xbrli:identifier>0000320193</xbrli:identifier></xbrli:entity>
          <xbrli:period><xbrli:instant>2024-12-31</xbrli:instant></xbrli:period>
        </xbrli:context>
        "#;
        let contexts = parse_contexts(xml);
        let context = contexts.get("ctx_20241231").unwrap();
        assert_eq!(context.entity_id.as_deref(), Some("0000320193"));
        assert_eq!(context.period_instant.as_deref(), Some("2024-12-31"));
    }

    #[test]
    fn parse_units_extracts_measure() {
        let xml = r#"
        <xbrli:unit id="u_usd">
          <xbrli:measure>iso4217:USD</xbrli:measure>
        </xbrli:unit>
        "#;
        let units = parse_units(xml);
        assert_eq!(units.get("u_usd").map(String::as_str), Some("iso4217:USD"));
    }

    #[test]
    fn infer_period_end_handles_as_of_format() {
        let value = infer_period_end_from_context("As_Of_11_1_2020_context");
        assert_eq!(value.as_deref(), Some("2020-11-01"));
    }
}
