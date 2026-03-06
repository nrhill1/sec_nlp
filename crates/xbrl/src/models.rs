use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct XbrlFact {
    pub tag: String,
    pub namespace: String,
    pub local_name: String,
    pub value: f64,
    pub raw_value: String,
    pub scale: i32,
    pub decimals: Option<i32>,
    pub unit: Option<String>,
    pub context_ref: String,
    pub period_start: Option<String>,
    pub period_end: Option<String>,
    pub period_instant: Option<String>,
    pub entity_id: Option<String>,
    pub segment: Option<String>,
}

impl XbrlFact {
    pub fn from_parts(
        tag: String,
        raw_value: String,
        context_ref: Option<String>,
        unit: Option<String>,
        scale: i32,
        decimals: Option<i32>,
    ) -> Option<Self> {
        let (namespace, local_name) = split_tag(&tag);
        let value = parse_numeric_value(&raw_value, scale)?;
        Some(Self {
            tag,
            namespace,
            local_name,
            value,
            raw_value,
            scale,
            decimals,
            unit,
            context_ref: context_ref.unwrap_or_default(),
            period_start: None,
            period_end: None,
            period_instant: None,
            entity_id: None,
            segment: None,
        })
    }

    pub fn apply_context(&mut self, context: &XbrlContext) {
        self.period_start = context.period_start.clone();
        self.period_end = context.period_end.clone();
        self.period_instant = context.period_instant.clone();
        self.entity_id = context.entity_id.clone();
        self.segment = context.segment.clone();
    }
}

#[derive(Debug, Clone, Serialize, Default)]
pub struct XbrlContext {
    pub id: String,
    pub entity_id: Option<String>,
    pub period_start: Option<String>,
    pub period_end: Option<String>,
    pub period_instant: Option<String>,
    pub segment: Option<String>,
}

pub fn split_tag(tag: &str) -> (String, String) {
    let mut parts = tag.splitn(2, ':');
    let left = parts.next().unwrap_or_default();
    let right = parts.next();
    match right {
        Some(local) => (left.to_string(), local.to_string()),
        None => (String::new(), left.to_string()),
    }
}

pub fn parse_numeric_value(raw_value: &str, scale: i32) -> Option<f64> {
    let trimmed = raw_value.trim();
    if trimmed.is_empty() {
        return None;
    }
    let is_parenthesized_negative = trimmed.starts_with('(') && trimmed.ends_with(')');
    let cleaned = trimmed
        .trim_start_matches('(')
        .trim_end_matches(')')
        .replace([',', '$', ' '], "");
    let lowered = cleaned.to_ascii_lowercase();
    if matches!(
        lowered.as_str(),
        "na" | "n/a" | "null" | "none" | "nil" | "inf" | "-inf" | "nan"
    ) {
        return None;
    }
    let mut value = cleaned.parse::<f64>().ok()?;
    if is_parenthesized_negative {
        value = -value.abs();
    }
    if scale != 0 {
        value *= 10_f64.powi(scale);
    }
    Some(value)
}
