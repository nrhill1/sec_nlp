use once_cell::sync::Lazy;
use std::collections::HashMap;

static TAG_NORMALIZATION: Lazy<HashMap<&'static str, &'static str>> = Lazy::new(|| {
    HashMap::from([
        (
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        ),
        ("us-gaap:Revenues", "us-gaap:Revenues"),
        ("us-gaap:SalesRevenueNet", "us-gaap:SalesRevenueNet"),
        ("us-gaap:NetIncomeLoss", "us-gaap:NetIncomeLoss"),
        ("ifrs-full:ProfitLoss", "ifrs-full:ProfitLoss"),
        (
            "us-gaap:EarningsPerShareBasic",
            "us-gaap:EarningsPerShareBasic",
        ),
        (
            "us-gaap:EarningsPerShareDiluted",
            "us-gaap:EarningsPerShareDiluted",
        ),
    ])
});

pub fn normalize_tag(tag: &str) -> String {
    let trimmed = tag
        .trim()
        .trim_start_matches('<')
        .trim_end_matches('>')
        .split_whitespace()
        .next()
        .unwrap_or_default();
    if trimmed.is_empty() {
        return String::new();
    }
    if let Some(normalized) = TAG_NORMALIZATION.get(trimmed) {
        return (*normalized).to_string();
    }
    if let Some((namespace, local_name)) = trimmed.split_once(':') {
        return format!("{}:{}", namespace.to_ascii_lowercase(), local_name);
    }
    trimmed.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalize_tag_lowercases_namespace() {
        let normalized = normalize_tag("US-GAAP:Revenues");
        assert_eq!(normalized, "us-gaap:Revenues");
    }
}
