use std::fs;

use newswatch::feeds::json_api;

#[test]
fn parses_newsapi_fixture() {
    let content = fs::read_to_string("tests/fixtures/sample_newsapi.json")
        .expect("json fixture should exist");

    let items = json_api::parse_feed(&content, "NewsAPI", "https://newsapi.org/v2/everything")
        .expect("json parsing should succeed");

    assert_eq!(items.len(), 2);
    assert!(items[0].title.contains("Acme"));
    assert!(items[0].url.starts_with("https://example.com/"));
}
