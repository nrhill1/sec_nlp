use newswatch::feeds::rss;

#[test]
fn parses_sample_rss_fixture() {
    let content = r#"<rss version="2.0"><channel><title>Sample RSS</title><link>https://example.com</link><description>News</description><item><title>Acme policy statement</title><link>https://example.com/1</link><pubDate>Fri, 25 Sep 2026 12:00:00 GMT</pubDate></item><item><title>Acme policy statement</title><link>https://example.com/2</link><pubDate>Thu, 24 Sep 2026 12:00:00 GMT</pubDate></item></channel></rss>"#;

    let items = rss::parse_feed(content, "Sample RSS", "https://example.com/feed.xml")
        .expect("rss parsing should succeed");

    assert_eq!(items.len(), 2);
    assert_ne!(items[0].published_at, items[1].published_at);
    assert_eq!(items[0].source, "Sample RSS");
    assert!(items[0].title.contains("Acme"));
    assert!(items[0].url.starts_with("https://example.com/"));
}
