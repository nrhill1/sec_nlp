# crate: `crates/xbrl` — Fast XBRL Fact Extraction

## Purpose

Replace and generalize the Python-side XBRL parsing currently embedded in the warranty pipeline (`src/sec_nlp/pipelines/presets/warranty/pipeline.py`, lines 337–524 and `steps/extract/xbrl.py`). That code is regex-based, tag-specific, and tightly coupled to warranty fields. This crate provides a general-purpose, high-throughput XBRL parser exposed to Python via PyO3.

## Existing Implementations — Build vs. Reuse

**`crabrl`** (https://github.com/stefanoamorelli/crabrl, crates.io) is a mature Rust XBRL parser claiming 50–150x faster than Arelle. It already provides `Parser::parse_file()` / `parse_bytes()`, context/unit resolution, and both generic and SEC EDGAR validation modes. It uses `quick-xml`, `ahash`, `compact_str`, `rayon`, and `mimalloc`.

**`fast_xbrl_parser`** (https://github.com/TiesdeKok/fast_xbrl_parser) is another Rust XBRL parser with Python bindings already built via PyO3. It outputs JSON/CSV and has SEC EDGAR support.

**Recommendation: Wrap `crabrl`, don't rewrite.** Use `crabrl` as a Cargo dependency for the core parsing. This crate becomes a thin integration layer that:
1. Adds the PyO3 bindings (since `crabrl` itself does not expose a `#[pymodule]`).
2. Adds taxonomy normalization (mapping tag variants to canonical financial line items like `revenue`, `net_income`, etc.) — domain logic `crabrl` intentionally omits.
3. Adds fact-to-Pydantic conversion helpers for the Python side.
4. Adds iXBRL detection heuristics and automatic format dispatch (HTML-with-inline-XBRL vs. traditional instance doc).

If `crabrl`'s API proves insufficient (e.g., missing iXBRL support or incomplete context resolution for SEC filings), fall back to the `quick-xml`-based custom parser as described below — but start with the wrapper approach.

Current status (February 13, 2026): initial implementation is using the custom parser path with PyO3 bindings and wrapper integration. `crabrl` wrapping is still an optional optimization pass.

## Existing Code to Study

- `src/sec_nlp/pipelines/presets/warranty/pipeline.py` — `_load_xbrl_for_filing()` method shows the inline XBRL regex parsing pattern and context resolution logic that this crate replaces.
- `src/sec_nlp/pipelines/presets/warranty/steps/extract/xbrl.py` — deterministic extraction from XBRL Document objects.
- `crates/efts/` — reference for PyO3 crate structure, `build.rs`, `Makefile`, and `Cargo.toml` layout.

## File Structure

```
crates/xbrl/
├── Cargo.toml
├── Makefile              # Copy from crates/efts/Makefile, update crate name
├── build.rs              # Copy from crates/efts/build.rs (identical Python-linking logic)
├── src/
│   ├── lib.rs            # PyO3 module definition, exports
│   ├── parser.rs         # Core parsing: iXBRL and traditional instance documents
│   ├── context.rs        # Context resolution: period, entity, segment
│   ├── taxonomy.rs       # US-GAAP / IFRS taxonomy tag mapping and normalization
│   ├── facts.rs          # Fact extraction, scaling, deduplication
│   ├── linkbase.rs       # Calculation linkbase validation
│   ├── models.rs         # Rust structs: XbrlFact, XbrlContext, XbrlDocument
│   ├── python.rs         # PyO3 class wrappers: PyXbrlParser, PyXbrlFact
│   └── error.rs          # Error types
├── tests/
│   ├── test_ixbrl.rs     # Inline XBRL parsing tests with fixture HTML
│   ├── test_instance.rs  # Traditional XBRL instance parsing
│   └── fixtures/         # Sample iXBRL and instance XML files
└── examples/
    └── xbrl_smoke.rs     # Quick smoke test against a local filing
```

## Key Types

```rust
// models.rs
#[derive(Debug, Clone, Serialize)]
pub struct XbrlFact {
    pub tag: String,             // e.g., "us-gaap:Revenues"
    pub namespace: String,       // e.g., "us-gaap"
    pub local_name: String,      // e.g., "Revenues"
    pub value: f64,
    pub raw_value: String,
    pub scale: i32,
    pub decimals: Option<i32>,
    pub unit: Option<String>,    // e.g., "USD", "shares"
    pub context_ref: String,
    pub period_start: Option<String>,  // ISO date
    pub period_end: Option<String>,    // ISO date
    pub period_instant: Option<String>,
    pub entity_id: Option<String>,     // CIK
    pub segment: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct XbrlContext {
    pub id: String,
    pub entity_id: Option<String>,
    pub period_start: Option<String>,
    pub period_end: Option<String>,
    pub period_instant: Option<String>,
    pub segment: Option<String>,
}

// python.rs — PyO3 wrapper
#[pyclass]
pub struct PyXbrlParser { /* config fields */ }

#[pymethods]
impl PyXbrlParser {
    #[new]
    fn new() -> Self { ... }

    /// Parse an HTML string containing inline XBRL and return facts.
    fn parse_ixbrl(&self, html: &str) -> PyResult<Vec<PyXbrlFact>> { ... }

    /// Parse a traditional XBRL instance XML string.
    fn parse_instance(&self, xml: &str) -> PyResult<Vec<PyXbrlFact>> { ... }

    /// Parse a file from disk (auto-detects iXBRL vs instance).
    fn parse_file(&self, path: &str) -> PyResult<Vec<PyXbrlFact>> { ... }
}
```

## Dependencies (Cargo.toml)

```toml
[dependencies]
pyo3 = { version = "0.23", features = ["extension-module"] }
quick-xml = "0.37"
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
chrono = "0.4"
regex = "1.10"
once_cell = "1.19"
```

## Implementation Steps

- [x] **Scaffold the crate.** Added `Cargo.toml`, `Makefile`, `build.rs`, and module layout under `crates/xbrl/src/`.
- [x] **Implement context parsing** (`context.rs`). Added context + unit extraction helpers and date inference with unit tests.
- [x] **Implement iXBRL parsing** (`parser.rs`). Added extraction for `ix:nonFraction`/`ix:nonNumeric`/`ix:fraction` with attribute handling, scaling, and context/unit hydration.
- [x] **Implement traditional instance parsing** (`parser.rs`). Added namespace-tag fact extraction with structural-tag filtering and context/unit hydration.
- [x] **Implement taxonomy normalization** (`taxonomy.rs`). Added namespace normalization and a baseline US-GAAP/IFRS tag map with tests.
- [x] **Implement fact extraction and scaling** (`facts.rs`). Added numeric normalization, deduplication, context/unit hydration, and exported `extract_facts` APIs via PyO3.
- [x] **Implement calculation linkbase validation** (`linkbase.rs`). Added placeholder validator hook and wired parser calls so warning logic can be expanded without API changes.
- [x] **Implement PyO3 wrappers** (`python.rs`, `lib.rs`). Added `XbrlFact`, `PyXbrlParser`, `extract_facts()`, and `extract_facts_from_file()` exports.
- [x] **Add to root Makefile.** Added `XBRL_DIR`/`XBRL_MANIFEST`, `rs-xbrl-%`, `build-ext` integration, and `verify-rs` coverage.
- [x] **Write Python wrapper** (`src/sec_nlp/core/edgar/xbrl_facts.py`). Added lazy-loaded adapter with Pydantic models and convenience functions.
- [x] **Add type stubs** (`types/xbrl/__init__.pyi`). Added native extension stubs and Python wrapper stubs.
- [x] **Write tests.** Added Rust unit tests under `crates/xbrl/src/*` and Python wrapper tests in `tests/core/edgar/test_xbrl_facts.py`.

## Integration Points

- The `financials` pipeline (new) uses this crate as its extraction engine.
- The warranty pipeline can be migrated to use the general `xbrl` crate instead of its inline regex parser, reducing ~200 lines of Python.
- The `corr` crate can consume time-series fact tables from this crate for financial ratio correlation.

## Testing Strategy

- Rust unit tests: inline XML/HTML strings covering each tag variant, scale factor, context type.
- Rust integration test: parse a real 10-K iXBRL file from `tests/fixtures/`.
- Python tests: mock the Rust extension (return canned `PyXbrlFact` objects), test the Pydantic conversion layer. No network calls (per `docs/AGENTS.md` rule 1).
