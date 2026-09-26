use serde_json::{json, Value};

fn load_fixture(_name: &str) -> Value {
    json!({"hits": {"total": {"value": 1}, "hits": [{"_source": {
        "adsh": "0001234567-24-000001", "cik": "1234567",
        "display_names": ["Example Company"], "form": "10-K", "file_date": "2024-01-15"
    }}]}})
}

#[test]
fn fixture_parses_hits() {
    let data = load_fixture("efts_sample.json");
    let response = efts::test_support::parse_response_value(&data, "warranty accrual")
        .expect("parse response");

    let total = response.get("total").and_then(Value::as_u64).unwrap_or(0);
    assert!(total >= 1);

    let hits = response
        .get("hits")
        .and_then(Value::as_array)
        .expect("hits array");
    assert!(!hits.is_empty());

    let first = hits[0].as_object().expect("hit object");
    let accession = first
        .get("accession_number")
        .and_then(Value::as_str)
        .unwrap_or("");
    let cik = first.get("cik").and_then(Value::as_str).unwrap_or("");
    let company = first
        .get("company_name")
        .and_then(Value::as_str)
        .unwrap_or("");
    let filed_date = first
        .get("filed_date")
        .and_then(Value::as_str)
        .unwrap_or("");

    assert!(accession.contains('-'));
    assert_eq!(cik.len(), 10);
    assert!(!company.is_empty());
    assert!(!filed_date.is_empty());

    let clean_accession = accession.replace('-', "");
    let cik_trimmed = cik.trim_start_matches('0');
    assert!(!cik_trimmed.is_empty());
    let url = format!(
        "https://www.sec.gov/Archives/edgar/data/{}/{}/",
        cik_trimmed, clean_accession
    );
    assert!(url.starts_with("https://www.sec.gov/Archives/edgar/data/"));
}
