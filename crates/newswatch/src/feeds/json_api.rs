use serde_json::Value;

use crate::error::NewswatchError;
use crate::models::NewsItem;

pub fn parse_feed(
    content: &str,
    source_name: &str,
    source_url: &str,
) -> Result<Vec<NewsItem>, NewswatchError> {
    let value: Value = serde_json::from_str(content)?;

    if let Some(articles) = value.get("articles").and_then(Value::as_array) {
        return Ok(parse_newsapi(articles, source_name, source_url));
    }

    if let Some(results) = value.get("results").and_then(Value::as_array) {
        return Ok(parse_polygon(results, source_name, source_url));
    }

    Ok(Vec::new())
}

fn parse_newsapi(articles: &[Value], source_name: &str, source_url: &str) -> Vec<NewsItem> {
    let mut items: Vec<NewsItem> = Vec::new();

    for article in articles {
        let Some(title) = article.get("title").and_then(Value::as_str) else {
            continue;
        };
        let normalized_title = title.trim();
        if normalized_title.is_empty() {
            continue;
        }

        let url = article
            .get("url")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .unwrap_or(source_url)
            .to_string();

        let published_at = article
            .get("publishedAt")
            .and_then(Value::as_str)
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty());

        let snippet = article
            .get("description")
            .and_then(Value::as_str)
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty());

        items.push(NewsItem {
            title: normalized_title.to_string(),
            url,
            source: source_name.to_string(),
            published_at,
            matched_keywords: Vec::new(),
            snippet,
        });
    }

    items
}

fn parse_polygon(results: &[Value], source_name: &str, source_url: &str) -> Vec<NewsItem> {
    let mut items: Vec<NewsItem> = Vec::new();

    for article in results {
        let Some(title) = article.get("title").and_then(Value::as_str) else {
            continue;
        };
        let normalized_title = title.trim();
        if normalized_title.is_empty() {
            continue;
        }

        let url = article
            .get("article_url")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .unwrap_or(source_url)
            .to_string();

        let published_at = article
            .get("published_utc")
            .and_then(Value::as_str)
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty());

        let snippet = article
            .get("description")
            .and_then(Value::as_str)
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty());

        items.push(NewsItem {
            title: normalized_title.to_string(),
            url,
            source: source_name.to_string(),
            published_at,
            matched_keywords: Vec::new(),
            snippet,
        });
    }

    items
}
