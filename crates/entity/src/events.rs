use once_cell::sync::Lazy;
use regex::Regex;

use crate::models::EventMention;

struct EventPattern {
    event_type: &'static str,
    regex: Regex,
}

static EVENT_PATTERNS: Lazy<Vec<EventPattern>> = Lazy::new(|| {
    vec![
        EventPattern {
            event_type: "merger",
            regex: Regex::new(
                r"(?i)\b(merger|acquisition|acquir(?:e|ed|ing)|business combination|joint venture)\b",
            )
            .expect("valid regex"),
        },
        EventPattern {
            event_type: "bankruptcy",
            regex: Regex::new(r"(?i)\b(bankruptcy|chapter\s+11|insolvency)\b")
                .expect("valid regex"),
        },
        EventPattern {
            event_type: "restatement",
            regex: Regex::new(r"(?i)\b(restatement|restate(?:d|ment)?|material weakness)\b")
                .expect("valid regex"),
        },
        EventPattern {
            event_type: "delisting",
            regex: Regex::new(
                r"(?i)\b(delist(?:ed|ing)?|nasdaq deficiency|nyse deficiency)\b",
            )
            .expect("valid regex"),
        },
        EventPattern {
            event_type: "dividend",
            regex: Regex::new(r"(?i)\b(dividend|special dividend)\b")
                .expect("valid regex"),
        },
        EventPattern {
            event_type: "stock_split",
            regex: Regex::new(r"(?i)\b(stock split|reverse split)\b")
                .expect("valid regex"),
        },
    ]
});

pub fn detect_events(text: &str) -> Vec<EventMention> {
    let mut events: Vec<EventMention> = Vec::new();

    for pattern in EVENT_PATTERNS.iter() {
        for m in pattern.regex.find_iter(text) {
            let phrase = m.as_str();
            events.push(EventMention {
                event_type: pattern.event_type.to_string(),
                text: phrase.to_string(),
                start: m.start(),
                end: m.end(),
                confidence: confidence_for_match(phrase),
            });
        }
    }

    events.sort_by_key(|event| {
        (
            event.start,
            event.end,
            event.event_type.clone(),
            event.text.clone(),
        )
    });
    events.dedup_by(|left, right| left.key() == right.key());
    events
}

fn confidence_for_match(phrase: &str) -> f64 {
    let normalized = phrase.trim().to_ascii_lowercase();
    if normalized.contains("chapter 11")
        || normalized.contains("business combination")
        || normalized.contains("material weakness")
        || normalized.contains("reverse split")
    {
        return 0.95;
    }
    if normalized.len() >= 10 {
        return 0.85;
    }
    0.75
}
