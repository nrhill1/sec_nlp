use newswatch::feeds::json_api;

#[test]
fn parses_newsapi_fixture() {
    let content = r#"{"articles":[{"title":"Acme earnings","url":"https://example.com/1","publishedAt":"2026-09-25T12:00:00Z"},{"title":"Acme policy update","url":"https://example.com/2","publishedAt":"2026-09-24T12:00:00Z"}]}"#;

    let items = json_api::parse_feed(content, "NewsAPI", "https://newsapi.org/v2/everything")
        .expect("json parsing should succeed");

    assert_eq!(items.len(), 2);
    assert!(items[0].title.contains("Acme"));
    assert!(items[0].url.starts_with("https://example.com/"));
}
