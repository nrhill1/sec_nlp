use std::collections::{HashMap, HashSet};

use crate::context::infer_period_end_from_context;
use crate::models::{XbrlContext, XbrlFact};

pub fn dedupe_facts(facts: Vec<XbrlFact>) -> Vec<XbrlFact> {
    let mut seen: HashSet<String> = HashSet::new();
    let mut output: Vec<XbrlFact> = Vec::new();

    for fact in facts {
        let key = format!(
            "{}|{}|{}|{}",
            fact.tag,
            fact.context_ref,
            fact.unit.as_deref().unwrap_or_default(),
            fact.value
        );
        if seen.insert(key) {
            output.push(fact);
        }
    }

    output
}

pub fn hydrate_facts(
    facts: Vec<XbrlFact>,
    contexts: &HashMap<String, XbrlContext>,
    units: &HashMap<String, String>,
) -> Vec<XbrlFact> {
    let mut hydrated: Vec<XbrlFact> = Vec::new();
    for mut fact in dedupe_facts(facts) {
        if let Some(context) = contexts.get(&fact.context_ref) {
            fact.apply_context(context);
        }

        if fact.period_end.is_none() {
            if let Some(period_end) = infer_period_end_from_context(&fact.context_ref) {
                fact.period_end = Some(period_end);
            }
        }

        let resolved_unit = fact
            .unit
            .as_ref()
            .and_then(|unit_ref| units.get(unit_ref))
            .cloned();
        if let Some(unit) = resolved_unit {
            fact.unit = Some(unit);
        }

        hydrated.push(fact);
    }
    hydrated
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::XbrlContext;

    #[test]
    fn hydrate_facts_applies_context_and_unit() {
        let facts = vec![XbrlFact::from_parts(
            "us-gaap:Revenues".to_string(),
            "100".to_string(),
            Some("ctx1".to_string()),
            Some("u_usd".to_string()),
            0,
            None,
        )
        .unwrap()];
        let contexts = HashMap::from([(
            "ctx1".to_string(),
            XbrlContext {
                id: "ctx1".to_string(),
                entity_id: Some("0000000001".to_string()),
                period_start: Some("2024-01-01".to_string()),
                period_end: Some("2024-12-31".to_string()),
                period_instant: None,
                segment: None,
            },
        )]);
        let units = HashMap::from([("u_usd".to_string(), "iso4217:USD".to_string())]);

        let hydrated = hydrate_facts(facts, &contexts, &units);
        assert_eq!(hydrated.len(), 1);
        assert_eq!(hydrated[0].unit.as_deref(), Some("iso4217:USD"));
        assert_eq!(hydrated[0].entity_id.as_deref(), Some("0000000001"));
        assert_eq!(hydrated[0].period_end.as_deref(), Some("2024-12-31"));
    }
}
