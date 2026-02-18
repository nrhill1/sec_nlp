use newswatch::dedup::dedupe_news_items;
use newswatch::models::NewsItem;

#[test]
fn removes_near_duplicate_headlines() {
    let items = vec![
        NewsItem {
            title: "Acme announces quarterly dividend".to_string(),
            url: "https://example.com/a".to_string(),
            source: "feed-a".to_string(),
            published_at: Some("2025-02-10T12:00:00Z".to_string()),
            matched_keywords: Vec::new(),
            snippet: None,
        },
        NewsItem {
            title: "Acme announces quarterly dividend increase".to_string(),
            url: "https://example.com/b".to_string(),
            source: "feed-b".to_string(),
            published_at: Some("2025-02-10T12:05:00Z".to_string()),
            matched_keywords: Vec::new(),
            snippet: None,
        },
    ];

    let deduped = dedupe_news_items(items, 8);

    assert_eq!(deduped.len(), 1);
}
