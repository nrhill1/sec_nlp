use entity::events;

#[test]
fn detects_event_phrases() {
    let text = "The board approved a merger and later announced a Chapter 11 filing.";

    let events = events::detect_events(text);

    assert!(events.iter().any(|event| event.event_type == "merger"));
    assert!(events.iter().any(|event| event.event_type == "bankruptcy"));
}
