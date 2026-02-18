use entity::tagger::CoreEntityTagger;

#[test]
fn tagger_combines_entities_and_events() {
    let text = "Mr. Smith disclosed $2.0 million and referenced Rule 10b-5 on 2024-03-01.";

    let tagger = CoreEntityTagger::new(None).expect("tagger initialization should succeed");
    let (entities, events) = tagger.tag_and_detect(text);

    assert!(entities.iter().any(|entity| entity.entity_type == "PERSON"));
    assert!(entities.iter().any(|entity| entity.entity_type == "MONEY"));
    assert!(entities
        .iter()
        .any(|entity| entity.entity_type == "REGULATION"));
    assert!(entities.iter().any(|entity| entity.entity_type == "DATE"));
    assert!(events.is_empty());
}
