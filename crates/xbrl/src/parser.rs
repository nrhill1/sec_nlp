use std::collections::HashMap;
use std::path::Path;

use once_cell::sync::Lazy;
use regex::Regex;

use crate::context::{parse_contexts, parse_units};
use crate::error::XbrlError;
use crate::facts::hydrate_facts;
use crate::linkbase::validate_calculations;
use crate::models::XbrlFact;
use crate::taxonomy::normalize_tag;

static IX_FACT_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r"(?is)<ix:(?:nonFraction|nonNumeric|fraction)\b(?P<attrs>[^>]*)>(?P<value>.*?)</ix:(?:nonFraction|nonNumeric|fraction)>",
    )
    .unwrap()
});

static INSTANCE_FACT_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r"(?is)<(?P<tag>[A-Za-z_][\w\.-]*:[A-Za-z_][\w\.-]*)\b(?P<attrs>[^>]*)>(?P<value>.*?)</[A-Za-z_][\w\.-]*:[A-Za-z_][\w\.-]*>",
    )
    .unwrap()
});

static ATTR_RE: Lazy<Regex> =
    Lazy::new(|| Regex::new(r#"([A-Za-z_:][\w:.-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')"#).unwrap());

static TAG_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"(?is)<[^>]+>").unwrap());

fn parse_attrs(attrs: &str) -> HashMap<String, String> {
    let mut map: HashMap<String, String> = HashMap::new();
    for captures in ATTR_RE.captures_iter(attrs) {
        let key = captures
            .get(1)
            .map(|m| m.as_str().to_string())
            .unwrap_or_default();
        let value = captures
            .get(2)
            .or_else(|| captures.get(3))
            .map(|m| m.as_str().to_string())
            .unwrap_or_default();
        map.insert(key, value);
    }
    map
}

fn get_attr(attrs: &HashMap<String, String>, name: &str) -> Option<String> {
    attrs.iter().find_map(|(key, value)| {
        if key.eq_ignore_ascii_case(name) {
            Some(value.clone())
        } else {
            None
        }
    })
}

fn parse_scale(attrs: &HashMap<String, String>) -> i32 {
    get_attr(attrs, "scale")
        .and_then(|value| value.parse::<i32>().ok())
        .unwrap_or(0)
}

fn parse_decimals(attrs: &HashMap<String, String>) -> Option<i32> {
    get_attr(attrs, "decimals").and_then(|value| value.parse::<i32>().ok())
}

fn clean_fact_value(raw: &str) -> String {
    TAG_RE
        .replace_all(raw, "")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .trim()
        .to_string()
}

fn is_structural_tag(tag: &str) -> bool {
    let lowered = tag.to_ascii_lowercase();
    lowered.starts_with("xbrli:")
        || lowered.starts_with("link:")
        || lowered.starts_with("ix:")
        || lowered.ends_with(":context")
        || lowered.ends_with(":unit")
        || lowered.ends_with(":entity")
        || lowered.ends_with(":period")
        || lowered.ends_with(":identifier")
        || lowered.ends_with(":measure")
        || lowered.ends_with(":segment")
        || lowered.ends_with(":startdate")
        || lowered.ends_with(":enddate")
        || lowered.ends_with(":instant")
}

pub fn parse_ixbrl(content: &str) -> Result<Vec<XbrlFact>, XbrlError> {
    let contexts = parse_contexts(content);
    let units = parse_units(content);
    let mut facts: Vec<XbrlFact> = Vec::new();

    for captures in IX_FACT_RE.captures_iter(content) {
        let attrs_text = captures
            .name("attrs")
            .map(|m| m.as_str())
            .unwrap_or_default();
        let attrs = parse_attrs(attrs_text);
        let raw_tag = get_attr(&attrs, "name")
            .or_else(|| get_attr(&attrs, "ix:name"))
            .unwrap_or_default();
        if raw_tag.is_empty() {
            continue;
        }

        let tag = normalize_tag(&raw_tag);
        let raw_value = captures
            .name("value")
            .map(|m| clean_fact_value(m.as_str()))
            .unwrap_or_default();
        let context_ref = get_attr(&attrs, "contextRef");
        let unit_ref = get_attr(&attrs, "unitRef");
        let scale = parse_scale(&attrs);
        let decimals = parse_decimals(&attrs);

        let fact =
            match XbrlFact::from_parts(tag, raw_value, context_ref, unit_ref, scale, decimals) {
                Some(fact) => fact,
                None => continue,
            };

        facts.push(fact);
    }

    let hydrated = hydrate_facts(facts, &contexts, &units);
    let _warnings = validate_calculations(&hydrated);
    Ok(hydrated)
}

pub fn parse_instance(content: &str) -> Result<Vec<XbrlFact>, XbrlError> {
    let contexts = parse_contexts(content);
    let units = parse_units(content);
    let mut facts: Vec<XbrlFact> = Vec::new();

    for captures in INSTANCE_FACT_RE.captures_iter(content) {
        let raw_tag = captures.name("tag").map(|m| m.as_str()).unwrap_or_default();
        if raw_tag.is_empty() || is_structural_tag(raw_tag) {
            continue;
        }

        let attrs_text = captures
            .name("attrs")
            .map(|m| m.as_str())
            .unwrap_or_default();
        let attrs = parse_attrs(attrs_text);

        let tag = normalize_tag(raw_tag);
        let raw_value = captures
            .name("value")
            .map(|m| clean_fact_value(m.as_str()))
            .unwrap_or_default();

        let context_ref = get_attr(&attrs, "contextRef");
        let unit_ref = get_attr(&attrs, "unitRef");
        let scale = parse_scale(&attrs);
        let decimals = parse_decimals(&attrs);

        let fact =
            match XbrlFact::from_parts(tag, raw_value, context_ref, unit_ref, scale, decimals) {
                Some(fact) => fact,
                None => continue,
            };

        facts.push(fact);
    }

    let hydrated = hydrate_facts(facts, &contexts, &units);
    let _warnings = validate_calculations(&hydrated);
    Ok(hydrated)
}

pub fn parse_auto(content: &str) -> Result<Vec<XbrlFact>, XbrlError> {
    if content.contains("<ix:") || content.contains("ix:nonFraction") {
        return parse_ixbrl(content);
    }
    parse_instance(content)
}

pub fn parse_file(path: &str) -> Result<Vec<XbrlFact>, XbrlError> {
    let file_path = Path::new(path);
    let content = std::fs::read_to_string(file_path)?;
    parse_auto(&content)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_ixbrl_basic() {
        let html = r#"
        <xbrli:context id="ctx_20241231">
          <xbrli:entity><xbrli:identifier>0000320193</xbrli:identifier></xbrli:entity>
          <xbrli:period><xbrli:instant>2024-12-31</xbrli:instant></xbrli:period>
        </xbrli:context>
        <xbrli:unit id="u_usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
        <ix:nonFraction name="us-gaap:Revenues" contextRef="ctx_20241231" unitRef="u_usd" scale="3">1,000</ix:nonFraction>
        "#;
        let facts = parse_ixbrl(html).unwrap();
        assert_eq!(facts.len(), 1);
        assert_eq!(facts[0].tag, "us-gaap:Revenues");
        assert_eq!(facts[0].value, 1_000_000.0);
        assert_eq!(facts[0].period_instant.as_deref(), Some("2024-12-31"));
        assert_eq!(facts[0].entity_id.as_deref(), Some("0000320193"));
        assert_eq!(facts[0].unit.as_deref(), Some("iso4217:USD"));
    }

    #[test]
    fn parse_instance_basic() {
        let xml = r#"
        <xbrl>
          <xbrli:context id="ctx_20241231">
            <xbrli:entity><xbrli:identifier>0000123456</xbrli:identifier></xbrli:entity>
            <xbrli:period><xbrli:instant>2024-12-31</xbrli:instant></xbrli:period>
          </xbrli:context>
          <xbrli:unit id="u_usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
          <us-gaap:NetIncomeLoss contextRef="ctx_20241231" unitRef="u_usd">250</us-gaap:NetIncomeLoss>
        </xbrl>
        "#;
        let facts = parse_instance(xml).unwrap();
        assert_eq!(facts.len(), 1);
        assert_eq!(facts[0].tag, "us-gaap:NetIncomeLoss");
        assert_eq!(facts[0].value, 250.0);
        assert_eq!(facts[0].period_instant.as_deref(), Some("2024-12-31"));
        assert_eq!(facts[0].entity_id.as_deref(), Some("0000123456"));
        assert_eq!(facts[0].unit.as_deref(), Some("iso4217:USD"));
    }
}
