use serde_json::{Map, Value};

use crate::models::SearchResponse;

use super::hit::parse_hit;
use super::util::get_u32;

pub(crate) fn parse_response(data: &Value, query: &str) -> SearchResponse {
    let empty = Map::new();
    let hits_data = data
        .get("hits")
        .and_then(|v| v.as_object())
        .unwrap_or(&empty);
    let total = extract_total(hits_data);
    let raw_hits = hits_data
        .get("hits")
        .and_then(|v| v.as_array())
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    let mut hits = Vec::new();
    for raw_hit in raw_hits {
        hits.push(parse_hit(raw_hit));
    }
    let query_data = data
        .get("query")
        .and_then(|v| v.as_object())
        .unwrap_or(&empty);
    let start = get_u32(query_data, "from", 0);
    let limit = get_u32(query_data, "size", 10);
    SearchResponse {
        query: query.to_string(),
        total,
        hits_vec: hits,
        start,
        limit,
    }
}

fn extract_total(hits_data: &Map<String, Value>) -> u64 {
    match hits_data.get("total") {
        Some(Value::Object(total)) => total
            .get("value")
            .and_then(|v| v.as_u64().or_else(|| v.as_f64().map(|f| f as u64)))
            .unwrap_or(0),
        Some(Value::Number(number)) => number
            .as_u64()
            .or_else(|| number.as_f64().map(|f| f as u64))
            .unwrap_or(0),
        _ => 0,
    }
}
