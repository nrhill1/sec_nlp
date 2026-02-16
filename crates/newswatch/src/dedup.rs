use std::collections::{hash_map::DefaultHasher, HashSet};
use std::hash::{Hash, Hasher};

use crate::models::NewsItem;

pub fn dedupe_news_items(items: Vec<NewsItem>, max_hamming_distance: u32) -> Vec<NewsItem> {
    let mut kept: Vec<(u64, HashSet<String>, NewsItem)> = Vec::new();

    for item in items {
        let fingerprint = simhash(&item.title);
        let tokens = token_set(&item.title);
        if kept
            .iter()
            .any(|(existing_fp, existing_tokens, _)| {
                hamming_distance(*existing_fp, fingerprint) <= max_hamming_distance
                    || token_jaccard(existing_tokens, &tokens) >= 0.8
            })
        {
            continue;
        }
        kept.push((fingerprint, tokens, item));
    }

    kept.into_iter().map(|(_, _, item)| item).collect()
}

fn simhash(title: &str) -> u64 {
    let mut weights = [0_i32; 64];

    for token in title.split_whitespace() {
        let Some(normalized) = normalize_token(token) else {
            continue;
        };

        let mut hasher = DefaultHasher::new();
        normalized.hash(&mut hasher);
        let hash = hasher.finish();

        for bit in 0..64 {
            if (hash >> bit) & 1 == 1 {
                weights[bit] += 1;
            } else {
                weights[bit] -= 1;
            }
        }
    }

    let mut fingerprint: u64 = 0;
    for (bit, weight) in weights.into_iter().enumerate() {
        if weight >= 0 {
            fingerprint |= 1_u64 << bit;
        }
    }
    fingerprint
}

fn hamming_distance(left: u64, right: u64) -> u32 {
    (left ^ right).count_ones()
}

fn normalize_token(token: &str) -> Option<String> {
    let normalized = token
        .trim_matches(|c: char| !c.is_alphanumeric())
        .to_ascii_lowercase();
    if normalized.is_empty() {
        return None;
    }
    Some(normalized)
}

fn token_set(title: &str) -> HashSet<String> {
    title
        .split_whitespace()
        .filter_map(normalize_token)
        .collect()
}

fn token_jaccard(left: &HashSet<String>, right: &HashSet<String>) -> f64 {
    if left.is_empty() || right.is_empty() {
        return 0.0;
    }
    let intersection = left.intersection(right).count() as f64;
    let union = left.union(right).count() as f64;
    if union == 0.0 {
        return 0.0;
    }
    intersection / union
}

#[cfg(test)]
mod tests {
    use std::collections::HashSet;

    use super::{hamming_distance, token_jaccard};

    #[test]
    fn computes_hamming_distance() {
        assert_eq!(hamming_distance(0, 0), 0);
        assert_eq!(hamming_distance(0b1010, 0b1000), 1);
    }

    #[test]
    fn computes_token_jaccard_similarity() {
        let left: HashSet<String> = ["acme", "announces", "quarterly", "dividend"]
            .into_iter()
            .map(str::to_string)
            .collect();
        let right: HashSet<String> = [
            "acme",
            "announces",
            "quarterly",
            "dividend",
            "increase",
        ]
        .into_iter()
        .map(str::to_string)
        .collect();

        assert!((token_jaccard(&left, &right) - 0.8).abs() < f64::EPSILON);
    }
}
