//! Offline fixture smoke check; live requests belong to the Python SEC transport.
use serde_json::{json, Value};

fn main() {
    let value = json!({"hits": {"total": {"value": 1}, "hits": [{"_source": {
        "adsh": "0001234567-24-000001", "cik": "1234567",
        "display_names": ["Example"], "form": "10-K", "file_date": "2024-01-15"
    }}]}});
    let response = efts::test_support::parse_response_value(&value, "warranty accrual")
        .expect("parse fixture");
    let hits = response
        .get("hits")
        .and_then(Value::as_array)
        .expect("hits");
    assert!(!hits.is_empty());
    println!("Offline EFTS parser smoke check: {} hits", hits.len());
}
