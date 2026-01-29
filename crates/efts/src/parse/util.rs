use serde_json::Value;

pub(crate) fn get_str(
    data: &serde_json::Map<String, Value>,
    key: &str,
    default: &str,
) -> String {
    data.get(key)
        .and_then(|v| v.as_str())
        .unwrap_or(default)
        .to_string()
}

pub(crate) fn get_optional_str(
    data: &serde_json::Map<String, Value>,
    key: &str,
) -> Option<String> {
    data.get(key)
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
}

pub(crate) fn get_u32(
    data: &serde_json::Map<String, Value>,
    key: &str,
    default: u32,
) -> u32 {
    data.get(key)
        .and_then(|v| v.as_u64().or_else(|| v.as_f64().map(|f| f as u64)))
        .map(|v| v as u32)
        .unwrap_or(default)
}

pub(crate) fn get_f64(data: &Value, key: &str, default: f64) -> f64 {
    data.get(key)
        .and_then(|v| v.as_f64().or_else(|| v.as_i64().map(|i| i as f64)))
        .unwrap_or(default)
}

pub(crate) fn value_to_string(value: &Value) -> Option<String> {
    if let Some(text) = value.as_str() {
        return Some(text.to_string());
    }
    if let Some(number) = value.as_i64() {
        return Some(number.to_string());
    }
    if let Some(number) = value.as_u64() {
        return Some(number.to_string());
    }
    if let Some(number) = value.as_f64() {
        return Some((number as i64).to_string());
    }
    None
}
