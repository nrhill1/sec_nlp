use entity::patterns::money;

#[test]
fn extracts_and_normalizes_money_mentions() {
    let text =
        "The company reported $1.5 million in restructuring charges and USD 250,000 in fees.";

    let entities = money::extract(text);

    assert_eq!(entities.len(), 2);
    assert_eq!(entities[0].entity_type, "MONEY");
    assert_eq!(entities[0].normalized.as_deref(), Some("1500000.00"));
    assert_eq!(entities[1].normalized.as_deref(), Some("250000.00"));
}
