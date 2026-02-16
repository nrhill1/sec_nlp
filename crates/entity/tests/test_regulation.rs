use entity::patterns::regulation;

#[test]
fn extracts_regulatory_mentions() {
    let text = "Pursuant to Rule 10b-5 and Section 13(a), the company complied with Regulation S-K and Item 1A.";

    let entities = regulation::extract(text);
    let normalized: Vec<String> = entities
        .iter()
        .map(|entity| entity.normalized.clone().unwrap_or_default())
        .collect();

    assert!(normalized.iter().any(|value| value == "Rule 10b-5"));
    assert!(normalized.iter().any(|value| value == "Section 13(a)"));
    assert!(normalized.iter().any(|value| value == "Regulation S-K"));
    assert!(normalized.iter().any(|value| value == "Item 1A"));
}
