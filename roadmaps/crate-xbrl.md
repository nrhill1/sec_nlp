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
crabrl = "0.1"          # Core XBRL parser — use as primary engine
quick-xml = "0.37"      # Fallback / iXBRL-specific parsing if crabrl gaps exist
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
chrono = "0.4"
regex = "1.10"
once_cell = "1.19"
```

## Implementation Steps

1. **Scaffold the crate.** Copy `Cargo.toml`, `Makefile`, and `build.rs` from `crates/efts/`. Update the crate name to `xbrl`. Add the `#[pymodule]` definition in `lib.rs` with placeholder exports.

2. **Implement context parsing** (`context.rs`). Parse `<xbrli:context>` elements from both iXBRL and instance documents. Resolve period (instant vs. duration) and entity identifiers. Write unit tests with inline XML fixtures.

3. **Implement iXBRL parsing** (`parser.rs`). Use `quick-xml` to stream-parse HTML. Match `<ix:nonFraction>`, `<ix:nonNumeric>`, and `<ix:fraction>` elements. Extract `name`, `contextRef`, `unitRef`, `scale`, `decimals`, and text content. Resolve against parsed contexts.

4. **Implement traditional instance parsing** (`parser.rs`). Parse `<xbrl>` root documents. Extract elements by namespace prefix (e.g., `us-gaap:`, `ifrs-full:`). Resolve `contextRef` and `unitRef`.

5. **Implement taxonomy normalization** (`taxonomy.rs`). Map common tag variants to canonical names (e.g., `Revenues`, `SalesRevenueNet`, `RevenueFromContractWithCustomerExcludingAssessedTax` → `revenue`). Support US-GAAP and IFRS namespaces.

6. **Implement fact extraction and scaling** (`facts.rs`). Apply `scale` attribute (multiply by 10^scale). Deduplicate facts with identical (tag, context, value) tuples. Expose `extract_facts(html_or_xml: &str) -> Vec<XbrlFact>`.

7. **Implement calculation linkbase validation** (`linkbase.rs`). Optional: parse `<calculationLink>` to verify parent-child sum relationships. Emit warnings for mismatches.

8. **Implement PyO3 wrappers** (`python.rs`). Wrap `XbrlFact` as `PyXbrlFact` with `#[pyclass]`. Implement `PyXbrlParser` with `parse_ixbrl()`, `parse_instance()`, and `parse_file()` methods. Register in `lib.rs`.

9. **Add to root Makefile.** Add `XBRL_DIR`, `XBRL_MANIFEST` variables. Add `rs-xbrl-%` delegation target. Include `maturin develop -m crates/xbrl/Cargo.toml` in the `build-ext` target.

10. **Write Python wrapper** (`src/sec_nlp/core/edgar/xbrl_facts.py`). Thin module that imports the `xbrl` extension, calls `PyXbrlParser`, and converts results to Pydantic models. Follow the pattern in `src/sec_nlp/core/market.py` (lazy import via `import_module`, error wrapping).

11. **Add type stubs** (`types/xbrl/__init__.pyi`).

12. **Write tests.** Rust: unit tests per module with XML/HTML fixture strings. Python: tests in `tests/` with mocked extension (no network). Verify parsing of real 10-K iXBRL excerpts.

## Integration Points

- The `financials` pipeline (new) uses this crate as its extraction engine.
- The warranty pipeline can be migrated to use the general `xbrl` crate instead of its inline regex parser, reducing ~200 lines of Python.
- The `corr` crate can consume time-series fact tables from this crate for financial ratio correlation.

## Testing Strategy

- Rust unit tests: inline XML/HTML strings covering each tag variant, scale factor, context type.
- Rust integration test: parse a real 10-K iXBRL file from `tests/fixtures/`.
- Python tests: mock the Rust extension (return canned `PyXbrlFact` objects), test the Pydantic conversion layer. No network calls (per `docs/AGENTS.md` rule 1).
