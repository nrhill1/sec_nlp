use feed_rs::parser;

use crate::error::NewswatchError;
use crate::models::NewsItem;

pub fn parse_feed(
    content: &str,
    source_name: &str,
    source_url: &str,
) -> Result<Vec<NewsItem>, NewswatchError> {
    let feed =
        parser::parse(content.as_bytes()).map_err(|err| NewswatchError::new(err.to_string()))?;

    let mut items: Vec<NewsItem> = Vec::new();
    for entry in feed.entries {
        let title = entry
            .title
            .as_ref()
            .map(|title| title.content.trim().to_string())
            .unwrap_or_default();
        if title.is_empty() {
            continue;
        }

        let link = entry
            .links
            .first()
            .map(|link| link.href.clone())
            .unwrap_or_else(|| source_url.to_string());

        let published_at = entry
            .published
            .or(entry.updated)
            .map(|date_time| date_time.to_rfc3339());

        let snippet = entry
            .summary
            .as_ref()
            .map(|summary| summary.content.trim().to_string())
            .or_else(|| {
                entry
                    .content
                    .iter()
                    .find_map(|content| content.body.as_ref())
                    .map(|body| body.trim().to_string())
            });

        items.push(NewsItem {
            title,
            url: link,
            source: source_name.to_string(),
            published_at,
            matched_keywords: Vec::new(),
            snippet,
        });
    }

    Ok(items)
}
