# sec-nlp Expansion Roadmap

New Rust crates and Python modules to extend the project beyond its current scope of filing analysis, exhibit indexing, and warranty extraction.

## Progress Snapshot (as of February 13, 2026)

- [x] `crates/corr` scaffolded with core PyO3 exports, root `Makefile` integration, and type stubs
- [x] `sec_nlp/core/stats/` module foundation implemented (`correlation.py`, `event_study.py`, `sector.py`, `cross_filing.py`)
- [x] `analyze` `market_correlation.py` migrated for cumulative return, return series, volume spike, and volatility calculations (with fallback path)
- [x] `crates/xbrl` scaffolded and integrated (`lib.rs`, `python.rs`, parser/context/unit hydration, root `Makefile` target, and tests)
- [x] `sec_nlp/core/edgar/xbrl_facts.py` wrapper + native/typing stubs (`types/xbrl/__init__.pyi`, `types/sec_nlp/core/edgar/xbrl_facts.pyi`)
- [x] `sec_nlp/pipelines/presets/financials/` scaffolded and wired end-to-end (download/extract/aggregate/output + tests)
- [x] `financials` CLI command added and registered in root command routing
- [x] `sec_nlp/pipelines/presets/insider/` scaffolded and wired end-to-end (download/parse/aggregate/correlate/output + tests)
- [x] `insider` CLI command added and registered in root command routing
- [x] `sec_nlp/pipelines/presets/holdings/` scaffolded and wired end-to-end (download/parse/diff/aggregate/output + tests)
- [x] `holdings` CLI command added and registered in root command routing
- [x] Analyze runnables `SectorCorrelationRunnable`, `FilingSentimentDiffRunnable`, `EarningsSurpriseRunnable`, `SupplyChainMapRunnable`, and `RegulatoryExposureRunnable` implemented and tested
- [x] `sec_nlp/core/edgar/economic.py` implemented for FRED series fetch, filing-date alignment, and macro-sensitivity correlation, including analyze `--macro-context` wiring
- [x] `sec_nlp/core/edgar/proxy.py` implemented for DEF 14A compensation/proposal/board parsing with say-on-pay extraction and tests
- [x] `crates/entity` scaffolded with PyO3 exports, pattern modules (money/date/regulation/person/security-id), dictionary matcher, event detection, and root `Makefile` integration
- [x] `sec_nlp/core/text/entity_extraction.py` wrapper implemented with lazy `entity` loading, document enrichment helpers, native stubs, and tests
- [x] `crates/newswatch` scaffolded with feed parsing, JSON adapter support, keyword filtering, SimHash deduplication, PyO3 client exports, and root `Makefile` integration
- [x] `sec_nlp/core/news/client.py` wrapper + native/typing stubs (`types/newswatch/__init__.pyi`, `types/sec_nlp/core/news/client.pyi`) implemented with tests
- [x] `sec_nlp/pipelines/presets/news/` scaffolded and wired end-to-end (fetch/match/correlate/output + tests)
- [x] `news` CLI command added and registered in root command routing
- [x] `sec_nlp/pipelines/presets/events/` scaffolded and wired end-to-end (scan/enrich/score/output + tests)
- [x] `events` CLI command added and registered in root command routing
- [ ] Remaining crates/modules/pipelines in this roadmap

---

## Rust Crates

### `crates/xbrl` — Fast XBRL Fact Extraction

A PyO3-native XBRL parser that extracts structured financial facts from inline XBRL and instance documents. The warranty pipeline currently handles XBRL in Python (`steps/extract/xbrl.py`); this crate generalizes that into a reusable, high-throughput engine.

**Capabilities:**
- Parse iXBRL (inline) and traditional XBRL instance documents
- Extract tagged financial facts (revenue, net income, EPS, total debt, cash and equivalents, operating income, etc.) by US-GAAP/IFRS taxonomy
- Resolve contexts (period, entity, segment) to produce time-series fact tables
- Calculation linkbase validation — verify that reported sums match their components
- Expose a `PyXbrlParser` class and `extract_facts()` function via PyO3

**Key dependencies:** `quick-xml`, `serde`, `chrono`, `pyo3`

**Integration points:**
- `sec_nlp/core/edgar/xbrl_facts.py` — Python wrapper that maps Rust output to Pydantic models
- Replaces and generalizes the warranty-specific XBRL extraction
- Feeds the `financials` pipeline (see Python section) and the correlation engine

---

### `crates/corr` — Statistical Correlation Engine

A numerics crate that computes correlation and basic time-series statistics, exposed to Python via PyO3. Replaces ad-hoc Python math in `market_correlation.py` with a consolidated, tested engine.

**Capabilities:**
- Pearson and Spearman rank correlation between arbitrary `f64` series
- Rolling-window returns, cumulative abnormal returns (CAR), and beta vs. benchmark
- Volatility metrics: standard deviation, average true range, Garman-Klass estimator
- Simple event-study helper: given an event date and two series, compute pre/post windows and test for significance (parametric t-test on means)
- Expose all functions as `#[pyfunction]` with `Vec<f64>` / `Vec<(i64, f64)>` signatures

**Key dependencies:** `pyo3`, `statrs` (distributions / hypothesis tests), `ndarray` (optional, for matrix ops)

**Integration points:**
- `sec_nlp/core/stats/correlation.py` — thin Python wrapper
- `market_correlation.py` — delegate CAR / volatility calculations to this crate
- Cross-company and sector-level correlation pipelines (see Python section)

---

### `crates/newswatch` — Financial News Keyword Monitor

An HTTP client that fetches and keyword-greps financial news from RSS feeds and JSON APIs, with built-in rate limiting and deduplication.

**Capabilities:**
- Configurable feed list: RSS/Atom (SEC press releases, PR Newswire, BusinessWire, Reuters RSS) and JSON APIs (NewsAPI, Polygon.io news)
- Keyword / regex filtering applied server-side when the API supports it, client-side otherwise
- SimHash-based headline deduplication (mirrors the pattern in `efts/src/ranking.rs`)
- Returns a flat `Vec<NewsItem>` with fields: `title`, `url`, `source`, `published_at`, `matched_keywords`, `snippet`
- Async fetching with `tokio` + `reqwest`; sync wrapper for CLI usage
- PyO3 class `NewsClient` with `fetch()` and `fetch_async()` methods

**Key dependencies:** `reqwest`, `tokio`, `serde`, `regex`, `quick-xml` (RSS parsing), `chrono`, `pyo3`, `pyo3-async-runtimes`

**Integration points:**
- `sec_nlp/core/news/client.py` — Python wrapper
- The `news` pipeline (see Python section) consumes this directly
- The `events` pipeline cross-references news hits with filing dates

---

### `crates/entity` — Financial Entity & Event Tagger

A rule-based and dictionary-based named-entity recognizer tuned for SEC filings and financial text, implemented in Rust for speed over large document sets.

**Capabilities:**
- Entity types: `ORG` (company names via CIK/ticker dictionary), `PERSON` (officer/director patterns), `MONEY` (dollar amounts with magnitude normalization), `DATE`, `REGULATION` (e.g., "Section 13(a)", "Rule 10b-5"), `CUSIP`/`ISIN`
- Pattern library compiled with `regex::RegexSet` for single-pass extraction
- Optional Aho-Corasick dictionary matching for large company/ticker lists (reuses the `pyahocorasick` concept already in the Python side)
- Event phrase detection: acquisition, merger, bankruptcy, restatement, delisting, dividend, stock split — outputs `EventMention { event_type, span, confidence }`
- PyO3 class `EntityTagger` with `tag_text()` → `Vec<Entity>` and `detect_events()` → `Vec<EventMention>`

**Key dependencies:** `aho-corasick`, `regex`, `serde`, `pyo3`

**Integration points:**
- `sec_nlp/core/text/entity_extraction.py` — Python wrapper
- Feeds the `events` pipeline and enriches analysis output metadata
- Can augment EFTS search results with tagged entities before ranking

---

## Python Modules

### `sec_nlp/core/stats/` — Statistical Correlation Utilities

A `core` subpackage that wraps `crates/corr` and adds higher-level helpers for filing-to-market and cross-filing analysis.

**Files:**
- `correlation.py` — Thin wrapper around the Rust `corr` crate (`pearson()`, `spearman()`, `rolling_returns()`, `car()`, `beta()`)
- `event_study.py` — Given a symbol, event date, and benchmark ticker, compute pre/post abnormal returns and significance; outputs an `EventStudyResult` Pydantic model
- `sector.py` — Group symbols by SIC code (from EDGAR metadata) and compute intra-sector correlation matrices on a chosen metric (price return, sentiment, filing frequency)
- `cross_filing.py` — Compare sentiment/risk scores across multiple filings for the same symbol over time; detect trend changes and inflection points

**Depends on:** `crates/corr`, `sec_nlp.core.market`, existing risk factor and sentiment scoring

---

### `sec_nlp/pipelines/presets/financials/` — Financial Fact Pipeline

A pipeline that extracts structured financial data from XBRL-tagged filings and produces normalized time-series tables.

**Steps:**
1. `download` — Reuse existing `sec_nlp.core.ingest.downloader` for 10-K/10-Q filings
2. `extract` — Call `crates/xbrl` to pull all tagged facts; normalize to a standard schema (fact name, period, value, unit, decimals)
3. `aggregate` — Pivot facts into a per-period table (rows = periods, columns = financial line items); compute derived ratios (current ratio, debt/equity, gross margin, operating margin, ROE)
4. `output` — Write CSV/JSON/YAML; optionally emit a delta report comparing the latest period to prior periods

**CLI:** `sec-nlp financials AAPL --periods 8 --ratios --output-format csv`

**Depends on:** `crates/xbrl`, existing download/ingest infrastructure

---

### `sec_nlp/pipelines/presets/news/` — News Monitoring Pipeline

A pipeline that monitors financial news sources for keyword matches around a target company and correlates news volume with filing dates and market moves.

**Steps:**
1. `fetch` — Use `crates/newswatch` to pull recent headlines from configured feeds, filtered by company name / ticker / topic keywords
2. `match` — Score each headline against the user's topic list using the EFTS keyword extractors (`crates/efts` ranking module)
3. `correlate` — Align news timestamps with filing dates and market data; compute news-volume-to-price-change correlation using `crates/corr`
4. `output` — Produce a timeline view (date → headlines + filing events + price snapshot) in YAML/JSON/CSV

**CLI:** `sec-nlp news AAPL --topics "supply chain" recall --days 90`

**Depends on:** `crates/newswatch`, `crates/corr`, `sec_nlp.core.market`

---

### `sec_nlp/pipelines/presets/insider/` — Insider Trading Pipeline

Leverages the existing `insider_parser.py` to build a full pipeline for insider transaction analysis.

**Steps:**
1. `download` — Fetch Forms 3, 4, 5 for a symbol
2. `parse` — Extract transactions via `InsiderParser` (already implemented)
3. `aggregate` — Build a per-insider transaction ledger; compute net buys/sells per officer, cluster buys around event windows
4. `correlate` — Cross-reference insider transaction dates with filing dates and price movement using `crates/corr`; flag unusual clusters (e.g., multiple officers selling before an 8-K)
5. `output` — Transaction ledger (CSV), insider summary (YAML/JSON), alert list

**CLI:** `sec-nlp insider AAPL --lookback-months 12m --alert-cluster-threshold 3`

**Depends on:** existing `insider_parser.py`, `crates/corr`, `sec_nlp.core.market`

---

### `sec_nlp/pipelines/presets/holdings/` — Institutional Holdings Pipeline

Leverages the existing `holdings_parser.py` to analyze 13F institutional ownership over time.

**Steps:**
1. `download` — Fetch 13F-HR filings for a list of institutional filers (by CIK) or find all 13F filers holding a given CUSIP via EFTS
2. `parse` — Extract info tables via `HoldingsParser` (already implemented)
3. `diff` — Compare consecutive quarterly filings to compute position changes (new positions, exits, increases, decreases)
4. `aggregate` — Summarize ownership concentration (top 10 holders, Herfindahl index), total institutional ownership percentage
5. `output` — Holdings snapshot (CSV), quarter-over-quarter diff report (YAML/JSON)

**CLI:** `sec-nlp holdings AAPL --quarters 4 --top-holders 20`

**Depends on:** existing `holdings_parser.py`, `crates/efts` (for CUSIP lookup), `sec_nlp.core.market` (for position value calculation)

---

### `sec_nlp/pipelines/presets/events/` — Event Detection & Timeline Pipeline

A pipeline that detects material corporate events from filings and news, then assembles a chronological event timeline.

**Steps:**
1. `scan` — Pull 8-K filings (current reports) and apply `crates/entity` event phrase detection to identify event types (M&A, earnings restatement, executive departure, material agreement, etc.)
2. `enrich` — For each detected event, pull surrounding news via `crates/newswatch` and market data via `sec_nlp.core.market`
3. `score` — Run event-study analysis using `crates/corr`: compute abnormal returns around each event date, flag statistically significant reactions
4. `output` — Chronological event timeline (JSON/YAML) with per-event fields: event_type, date, filing_accession, headline_matches, car_5d, car_30d, volume_spike

**CLI:** `sec-nlp events AAPL --lookback 2y --event-types merger restatement executive`

**Depends on:** `crates/entity`, `crates/newswatch`, `crates/corr`, `sec_nlp.core.market`, existing EFTS and download infrastructure

---

### `sec_nlp/core/text/entity_extraction.py` — Entity Extraction Wrapper

A thin Python module wrapping `crates/entity` and integrating with the existing text processing layer.

**Capabilities:**
- `extract_entities(text) → list[Entity]` — calls Rust tagger, returns Pydantic models
- `detect_events(text) → list[EventMention]` — calls Rust event detector
- `enrich_documents(docs: list[Document]) → list[Document]` — adds `entities` and `events` keys to document metadata
- Integrates with the analyze pipeline as an optional post-processing step

---

### `sec_nlp/core/edgar/economic.py` — Economic Indicator Integration

A module that fetches macroeconomic time series (FRED API) and aligns them with filing and market data for contextual analysis.

**Capabilities:**
- `FredClient` — async HTTP client for the FRED API (Federal Reserve Economic Data); fetches series like GDP, CPI, unemployment rate, federal funds rate, yield curve spreads
- `align_to_filings(series, filings)` — given an economic series and a list of filing dates, produce a table mapping each filing period to the contemporaneous economic values
- `compute_macro_sensitivity(returns, indicator_series)` — correlation between a stock's returns and a macro indicator over rolling windows

**CLI addition:** `sec-nlp analyze AAPL --macro-context` flag adds economic backdrop to LLM context

**Depends on:** `crates/corr` (for correlation), `sec_nlp.core.market` (for aligning dates)

---

### `sec_nlp/core/edgar/proxy.py` — Proxy Statement (DEF 14A) Parser

A parser for proxy statements that extracts executive compensation tables, shareholder proposals, and board composition.

**Capabilities:**
- Extract executive compensation summary tables (name, title, salary, bonus, stock awards, total)
- Parse shareholder proposal descriptions and vote results
- Board of directors roster with committee memberships
- Say-on-pay vote results

**Integration:** New `proxy` pipeline or enrichment step within the existing `analyze` pipeline

---

## Runnables & Mini-Pipelines

These are lightweight, single-purpose runnables (following the existing `RunnableSerializable` pattern in `sec_nlp/pipelines/presets/analyze/runnables/`) that can be composed into larger pipelines or run standalone.

### `SectorCorrelationRunnable`
Computes pairwise price-return correlation for a set of symbols within a sector. Inputs: list of symbols, date range. Outputs: correlation matrix as a nested dict.

### `FilingSentimentDiffRunnable`
Compares LLM sentiment scores between two consecutive filings of the same type for a symbol. Inputs: two `AnalysisResultDict` lists. Outputs: per-topic sentiment delta, new/removed risk factors.

### `EarningsSupriseRunnable`
Compares XBRL-extracted EPS against analyst consensus (if available via market extension) and computes the surprise factor. Inputs: symbol, period. Outputs: reported EPS, expected EPS, surprise percentage, post-earnings CAR.

### `SupplyChainMapRunnable`
Uses exhibit documents (subsidiary lists from the `exb` pipeline) and entity extraction to build a first-degree supplier/customer graph. Inputs: symbol. Outputs: list of related entities with relationship type and source filing.

### `RegulatoryExposureRunnable`
Scans filing text for regulatory references (via `crates/entity` REGULATION entities) and groups them by regulatory body / statute. Inputs: list of Documents. Outputs: regulatory reference frequency table with trend comparison across filings.

---

## Large-Scale Retrieval: EFTS → Embed → Match

The most efficient architecture for matching arbitrary queries against a large filing corpus is a **two-stage retrieve-then-rank pipeline**: use EFTS as a cheap lexical first pass to narrow candidates, then embed only the surviving sections and rank by vector similarity. This avoids the cost of embedding the entire corpus upfront while still getting semantic matching where it matters.

### Why two stages?

Embedding every section of every filing is expensive — a single 10-K can have hundreds of chunks, and EDGAR holds millions of filings. EFTS full-text search is nearly free (server-side, sub-second) and eliminates 95%+ of irrelevant documents before any embedding work happens. The remaining candidate sections are small enough to embed on the fly or to pre-index incrementally.

### `crates/embed` — ONNX-Based Batch Embedding Engine

A Rust crate that runs embedding models locally via ONNX Runtime, bypassing the Python/Ollama overhead for high-throughput batch workloads.

**Capabilities:**
- Load any ONNX-exported embedding model (e.g., BGE-M3, MxBai, GTE, E5) from a local path
- Batch tokenization and inference with configurable batch size and thread count
- Normalize output vectors to unit length for cosine similarity
- Return `Vec<Vec<f32>>` to Python; optionally write embeddings to a memory-mapped file for zero-copy access
- PyO3 class `EmbeddingEngine` with `embed_batch(texts: Vec<String>) -> Vec<Vec<f32>>`

**Key dependencies:** `ort` (ONNX Runtime Rust bindings), `tokenizers` (HuggingFace tokenizer), `ndarray`, `pyo3`

**Performance target:** 500–2,000 chunks/sec on CPU for a 384-dim model (vs. ~50–100/sec through Ollama HTTP round-trips)

### `sec_nlp/pipelines/presets/retrieve/` — EFTS-to-Vector Retrieval Pipeline

A pipeline that combines EFTS lexical search with embedding-based re-ranking to return the most relevant accessions and sections for a set of queries.

**Steps:**
1. `candidate_search` — Execute EFTS queries (via `crates/efts`) with broad filters (form types, date range, tickers) to collect candidate accessions and snippets. Use `batch_search_async` for multiple queries in parallel. Target: top 200–500 hits per query.
2. `download_and_chunk` — For each candidate accession, download the filing (if not already cached) and chunk it using the existing `sec_nlp.core.text.chunking` module. Section extraction (`section_extractor.py`) can limit to specific items (e.g., Item 1A, Item 7) to reduce chunk volume.
3. `embed` — Batch-embed all candidate chunks using `crates/embed`. If a persistent Qdrant collection already contains embeddings for a given accession+chunk, skip re-embedding (incremental indexing).
4. `index` — Upsert embeddings into Qdrant (in-memory or persistent) using the existing `sec_nlp.pipelines.vector` infrastructure. Payloads include accession number, section, chunk index, filing date, ticker, form type.
5. `query` — Embed the user's query strings, run ANN search against the indexed chunks, and return ranked results with scores. Apply optional metadata filters (date range, form type) at query time via Qdrant payload filters.
6. `output` — Return matched accessions with per-chunk relevance scores, section references, and snippets. Output formats: JSON/YAML ranked list, or feed directly into the `analyze` pipeline as pre-filtered input.

**CLI:** `sec-nlp retrieve "supply chain disruption" --tickers AAPL MSFT --forms 10-K 10-Q --top-k 20`

**Depends on:** `crates/efts`, `crates/embed`, existing chunking/section extraction, existing Qdrant vector infrastructure

### Scaling strategies

**Incremental index build:** Rather than embedding the full corpus at once, build the index incrementally — each pipeline run adds new accessions to the persistent Qdrant collection. A filing's chunks are keyed by `(accession_number, chunk_index)` so re-runs are idempotent.

**Tiered storage:** Use Qdrant's on-disk index mode for collections exceeding available RAM. HNSW parameters can be tuned (m=16, ef_construct=128) for the typical filing chunk distribution (~100–500 dim, millions of vectors).

**Quantization:** Qdrant supports scalar and product quantization for large collections. For 384-dim BGE embeddings, scalar quantization cuts memory ~4x with minimal recall loss — critical for indexing hundreds of thousands of filings on a laptop.

**Pre-filtered embedding cache:** Store computed embeddings as sidecar files alongside downloads (`downloads/sec-edgar-filings/AAPL/10-K/<accession>/.embeddings.bin`). The `embed` step checks for this file before calling ONNX, making repeated queries against the same corpus near-instant.

### `EftsRetrieveRunnable`

A composable runnable (following the `RunnableSerializable` pattern) that encapsulates the full two-stage flow. Inputs: query strings, filter config. Outputs: ranked list of `RetrievalHit` Pydantic models (accession, section, chunk_text, score). Can be wired into the analyze pipeline's chain as a replacement for the current EFTS-only search step.

---

## Build System Additions

Each new Rust crate follows the existing pattern:
- `crates/<name>/Cargo.toml` with `crate-type = ["cdylib"]` and `pyo3` dependency
- `crates/<name>/Makefile` mirroring `crates/efts/Makefile`
- Root `Makefile` additions: `rs-<alias>-%` delegation target, inclusion in `build-ext`
- `maturin develop -m crates/<name>/Cargo.toml` for local dev
- Type stubs in `types/<name>/__init__.pyi`

Python modules follow the existing patterns:
- Pipeline presets in `sec_nlp/pipelines/presets/<name>/` with `config.py`, `models.py`, `pipeline.py`, `steps/`, `io/`
- CLI commands in `sec_nlp/cli/commands/<name>.py`
- Core modules in `sec_nlp/core/<subpackage>/`
- Tests mirroring source layout under `tests/`
