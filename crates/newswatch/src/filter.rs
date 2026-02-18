use regex::RegexSet;

use crate::error::NewswatchError;
use crate::models::NewsItem;

pub fn apply_keyword_filter(
    items: Vec<NewsItem>,
    keywords: &[String],
) -> Result<Vec<NewsItem>, NewswatchError> {
    if keywords.is_empty() {
        return Ok(items);
    }

    let normalized_keywords: Vec<String> = keywords
        .iter()
        .map(|keyword| keyword.trim())
        .filter(|keyword| !keyword.is_empty())
        .map(ToOwned::to_owned)
        .collect();

    if normalized_keywords.is_empty() {
        return Ok(items);
    }

    let patterns: Vec<String> = normalized_keywords
        .iter()
        .map(|keyword| format!("(?i){}", regex::escape(keyword)))
        .collect();
    let regex_set = RegexSet::new(patterns)?;

    let mut filtered: Vec<NewsItem> = Vec::new();
    for mut item in items {
        let mut haystack = item.title.clone();
        if let Some(snippet) = item.snippet.as_deref() {
            haystack.push(' ');
            haystack.push_str(snippet);
        }

        let matched_indices: Vec<usize> = regex_set.matches(&haystack).into_iter().collect();
        if matched_indices.is_empty() {
            continue;
        }

        item.matched_keywords = matched_indices
            .into_iter()
            .filter_map(|index| normalized_keywords.get(index).cloned())
            .collect();
        filtered.push(item);
    }

    Ok(filtered)
}
