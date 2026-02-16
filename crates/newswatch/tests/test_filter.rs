use newswatch::filter::apply_keyword_filter;
use newswatch::models::NewsItem;

#[test]
fn filters_items_and_populates_matched_keywords() {
    let items = vec![
        NewsItem {
            title: "Acme supply chain update".to_string(),
            url: "https://example.com/1".to_string(),
            source: "feed".to_string(),
            published_at: Some("2025-02-10T12:00:00Z".to_string()),
            matched_keywords: Vec::new(),
            snippet: Some("Supplier diversification details".to_string()),
        },
        NewsItem {
            title: "Unrelated macro article".to_string(),
            url: "https://example.com/2".to_string(),
            source: "feed".to_string(),
            published_at: Some("2025-02-10T11:00:00Z".to_string()),
            matched_keywords: Vec::new(),
            snippet: Some("No company mention".to_string()),
        },
    ];

    let filtered = apply_keyword_filter(items, &["supply chain".to_string(), "acme".to_string()])
        .expect("filter should succeed");

    assert_eq!(filtered.len(), 1);
    assert_eq!(filtered[0].matched_keywords.len(), 2);
}
