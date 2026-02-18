use std::fs;

use newswatch::feeds::rss;

#[test]
fn parses_sample_rss_fixture() {
    let content =
        fs::read_to_string("tests/fixtures/sample_rss.xml").expect("rss fixture should exist");

    let items = rss::parse_feed(&content, "Sample RSS", "https://example.com/feed.xml")
        .expect("rss parsing should succeed");

    assert_eq!(items.len(), 2);
    assert_eq!(items[0].source, "Sample RSS");
    assert!(items[0].title.contains("Acme"));
    assert!(items[0].url.starts_with("https://example.com/"));
}
