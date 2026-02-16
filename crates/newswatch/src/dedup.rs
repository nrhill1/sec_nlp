use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};

use crate::models::NewsItem;

pub fn dedupe_news_items(items: Vec<NewsItem>, max_hamming_distance: u32) -> Vec<NewsItem> {
    let mut kept: Vec<(u64, NewsItem)> = Vec::new();

    for item in items {
        let fingerprint = simhash(&item.title);
        if kept
            .iter()
            .any(|(existing, _)| hamming_distance(*existing, fingerprint) <= max_hamming_distance)
        {
            continue;
        }
        kept.push((fingerprint, item));
    }

    kept.into_iter().map(|(_, item)| item).collect()
}

fn simhash(title: &str) -> u64 {
    let mut weights = [0_i32; 64];

    for token in title.split_whitespace() {
        let normalized = token
            .trim_matches(|c: char| !c.is_alphanumeric())
            .to_ascii_lowercase();
        if normalized.is_empty() {
            continue;
        }

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

#[cfg(test)]
mod tests {
    use super::hamming_distance;

    #[test]
    fn computes_hamming_distance() {
        assert_eq!(hamming_distance(0, 0), 0);
        assert_eq!(hamming_distance(0b1010, 0b1000), 1);
    }
}
