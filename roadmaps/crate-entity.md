# crate: `crates/entity` — Financial Entity & Event Tagger

## Purpose

A rule-based and dictionary-based named-entity recognizer optimized for SEC filings. Extracts organizations, people, monetary amounts, dates, regulatory references, and security identifiers at high speed using compiled regex and Aho-Corasick automata. Also detects event phrases (merger, bankruptcy, etc.).

## Existing Implementations — Build vs. Reuse

**`rust-bert`** (crates.io) provides transformer-based NER (BERT finetuned on CoNLL03) with Person/Location/Organization/Misc extraction. High accuracy but heavy: requires `libtorch` or ONNX Runtime, ~500MB+ model download, and significant inference latency per document.

**`quickner`** (crates.io) is a Rust+PyO3 NER annotation tool with dictionary-based and regex/fuzzy matching. More of an annotation pipeline than an extraction library.

**Recommendation: Custom implementation.** No existing Rust crate provides SEC-domain-specific entity types (REGULATION, CUSIP/ISIN, MONEY with magnitude normalization, fiscal date references) or event phrase detection tuned to filing language. `rust-bert` is too heavy for batch processing thousands of filing chunks and covers the wrong entity taxonomy. The rule-based + Aho-Corasick approach is the right trade-off for this domain: fast, deterministic, no model dependencies, and easily extensible with new patterns. If higher-accuracy general NER is later needed (e.g., for person names in unstructured narrative), `rust-bert` with ONNX backend could be added as an optional feature behind a cargo feature flag.

## Existing Code to Study

- `src/sec_nlp/core/text/keyword.py` — existing Python keyword matching using `pyahocorasick`. This crate is the Rust equivalent for entity-level matching.
- `src/sec_nlp/core/text/risk_factors.py` — tokenization and sentence splitting patterns used in SEC text processing.
- `crates/efts/src/ranking.rs` — keyword extraction (YAKE, RAKE, etc.) and scoring patterns.

## File Structure

```
crates/entity/
├── Cargo.toml
├── Makefile
├── build.rs
├── src/
│   ├── lib.rs              # PyO3 module definition
│   ├── tagger.rs           # EntityTagger: main entry point
│   ├── patterns/
│   │   ├── mod.rs
│   │   ├── money.rs        # Dollar amount regex ($X million/billion, etc.)
│   │   ├── date.rs         # Date patterns (ISO, US formats, fiscal year refs)
│   │   ├── regulation.rs   # "Section 13(a)", "Rule 10b-5", "Regulation S-K"
│   │   ├── person.rs       # Officer/director name patterns
│   │   └── security_id.rs  # CUSIP (9 chars), ISIN (12 chars) validation
│   ├── dictionary.rs       # Aho-Corasick matcher for company/ticker lists
│   ├── events.rs           # Event phrase detection
│   ├── models.rs           # Entity, EntityType, EventMention, Span
│   ├── python.rs           # PyO3 classes
│   └── error.rs
├── data/
│   └── README.md           # Instructions for populating ticker/CIK dictionaries
└── tests/
    ├── test_money.rs
    ├── test_regulation.rs
    ├── test_events.rs
    └── test_tagger.rs
```

## Key Types

```rust
// models.rs
#[derive(Debug, Clone, Serialize)]
#[pyclass]
pub struct Entity {
    #[pyo3(get)] pub entity_type: String,  // "ORG", "PERSON", "MONEY", "DATE", "REGULATION", "CUSIP", "ISIN"
    #[pyo3(get)] pub text: String,         // matched text span
    #[pyo3(get)] pub start: usize,         // byte offset
    #[pyo3(get)] pub end: usize,
    #[pyo3(get)] pub normalized: Option<String>,  // e.g., dollar amount → "1500000.0"
}

#[derive(Debug, Clone, Serialize)]
#[pyclass]
pub struct EventMention {
    #[pyo3(get)] pub event_type: String,   // "merger", "bankruptcy", "restatement", etc.
    #[pyo3(get)] pub text: String,
    #[pyo3(get)] pub start: usize,
    #[pyo3(get)] pub end: usize,
    #[pyo3(get)] pub confidence: f64,      // 0.0–1.0
}

// python.rs
#[pyclass]
pub struct EntityTagger { /* compiled patterns, dictionary */ }

#[pymethods]
impl EntityTagger {
    #[new]
    fn new(dictionary_path: Option<String>) -> PyResult<Self>;

    fn tag_text(&self, text: &str) -> PyResult<Vec<Entity>>;
    fn detect_events(&self, text: &str) -> PyResult<Vec<EventMention>>;
    fn tag_and_detect(&self, text: &str) -> PyResult<(Vec<Entity>, Vec<EventMention>)>;
}
```

## Dependencies (Cargo.toml)

```toml
[dependencies]
pyo3 = { version = "0.23", features = ["extension-module"] }
aho-corasick = "1.1"
regex = "1.10"
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
once_cell = "1.19"
```

## Implementation Steps

- [x] **Scaffold the crate.** Boilerplate from `crates/efts/`.
- [x] **Implement `models.rs`.** Define `Entity`, `EntityType` (enum), `EventMention`, `Span`. Derive `#[pyclass]` on output types.
- [x] **Implement money patterns** (`patterns/money.rs`). Regex for: `$1.5 million`, `$1,500,000`, `$1.5B`, `USD 1.5 million`, etc. Normalize to a float value. Handle negative amounts.
- [x] **Implement regulation patterns** (`patterns/regulation.rs`). Regex for: `Section \d+(\([a-z]\))?` of the Exchange/Securities Act, `Rule \d+[a-z]-\d+`, `Regulation [A-Z](-[A-Z])?`, `Item \d+[A-Z]?`. Return the matched regulatory reference.
- [x] **Implement date patterns** (`patterns/date.rs`). ISO dates, US dates (MM/DD/YYYY), fiscal references ("fiscal year 2024", "FY2024", "three months ended March 31, 2024"). Normalize to ISO format.
- [x] **Implement person patterns** (`patterns/person.rs`). Title patterns: "Mr./Ms./Dr. LastName", "FirstName LastName, (CEO|CFO|President|Director)". Context-dependent — look for surrounding officer/director title keywords.
- [x] **Implement security ID patterns** (`patterns/security_id.rs`). CUSIP: 9 alphanumeric characters with check digit validation. ISIN: 2-letter country + 9 chars + check digit.
- [x] **Implement dictionary matcher** (`dictionary.rs`). Load a company/ticker dictionary (JSON lines: `{"name": "Apple Inc.", "ticker": "AAPL", "cik": "0000320193"}`). Build an `AhoCorasick` automaton. Match against text, emit `ORG` entities with the matched company name and metadata.
- [x] **Implement event detection** (`events.rs`). Phrase list per event type (merger: "merger", "acquisition", "acquir", "business combination"; bankruptcy: "bankruptcy", "Chapter 11", "insolvency"; restatement: "restatement", "restate", "material weakness"; etc.). Build a `RegexSet` for each category. Score by specificity (exact phrase > partial match). Return `EventMention` with confidence.
- [x] **Implement `tagger.rs`.** Orchestrate all pattern modules and dictionary. Single-pass where possible (run all regex sets, then Aho-Corasick, then merge/deduplicate overlapping spans). Sort results by start offset.
- [x] **Implement `python.rs`.** `EntityTagger` PyO3 class. `tag_text()`, `detect_events()`, `tag_and_detect()`. Register in `lib.rs`.
- [x] **Add to root Makefile.** `ENTITY_DIR`, `ENTITY_MANIFEST`, `rs-ent-%` target, include in `build-ext`.
- [x] **Write Python wrapper** (`src/sec_nlp/core/text/entity_extraction.py`).
- [x] **Add type stubs** (`types/entity/__init__.pyi`).
- [x] **Write tests.** Rust: per-pattern tests with known SEC filing excerpts. Python: mock extension. No network.

## Testing Strategy

- Each pattern module has its own test file with positive and negative examples from real SEC filing text.
- Event detection tests use 8-K filing excerpts containing known event phrases.
- Dictionary tests use a small fixture dictionary (5–10 companies).
- Integration test: full `tag_and_detect()` on a paragraph from a 10-K risk factors section.
