# crate: `crates/newswatch` — Financial News Keyword Monitor

## Purpose

Provide a high-performance HTTP client that fetches financial news from RSS feeds and JSON APIs, applies keyword/regex filtering, deduplicates headlines, and returns structured results to Python. Enables the `news` and `events` pipelines.

## Existing Implementations — Build vs. Reuse

**`feed-rs`** (crates.io, ~9K downloads/month) is the most mature Rust feed parser. Handles Atom, RSS 2.0/1.0/0.x, and JSON Feed with serde support. Auto-detects format. Supports Dublin Core and Media RSS extensions.

**`rss`** (crates.io, `rust-syndication/rss`) is an established RSS 2.0 serialization/deserialization library with validation and extension support.

**Recommendation: Use `feed-rs` as the parsing layer.** Do not write custom RSS/Atom parsing — `feed-rs` handles format detection, date parsing, and extension extraction. This crate adds the orchestration layer on top:
1. HTTP fetching with rate limiting and retries (reuse patterns from `crates/efts/src/http.rs`).
2. JSON API adapters for NewsAPI/Polygon (not covered by any feed crate).
3. Keyword/regex filtering and SimHash deduplication.
4. PyO3 bindings.

The RSS parsing in the file structure below (`feeds/rss.rs`) becomes a thin adapter around `feed-rs::parser::parse()` rather than a from-scratch parser.

## Existing Code to Study

- `crates/efts/src/http.rs` and `http_async.rs` — HTTP client with rate limiting and retries. Reuse the same pattern for news endpoint requests.
- `crates/efts/src/ranking.rs` — keyword extraction and scoring. The SimHash concept can be adapted for headline deduplication.
- `crates/efts/src/python.rs` — pattern for exposing an async Rust client to Python via PyO3.

## File Structure

```
crates/newswatch/
├── Cargo.toml
├── Makefile
├── build.rs
├── src/
│   ├── lib.rs            # PyO3 module definition
│   ├── client.rs         # Top-level NewsClient orchestrator
│   ├── feeds/
│   │   ├── mod.rs
│   │   ├── rss.rs        # RSS/Atom feed parser (quick-xml)
│   │   └── json_api.rs   # JSON API adapters (NewsAPI, Polygon)
│   ├── filter.rs         # Keyword and regex filtering
│   ├── dedup.rs          # SimHash-based headline deduplication
│   ├── models.rs         # NewsItem, FeedConfig, FilterConfig
│   ├── http.rs           # reqwest wrapper with rate limiting
│   ├── python.rs         # PyO3 class: NewsClient
│   └── error.rs
└── tests/
    ├── test_rss.rs
    ├── test_filter.rs
    ├── test_dedup.rs
    └── fixtures/
        ├── sample_rss.xml
        └── sample_newsapi.json
```

## Key Types

```rust
// models.rs
#[derive(Debug, Clone, Serialize)]
#[pyclass]
pub struct NewsItem {
    #[pyo3(get)] pub title: String,
    #[pyo3(get)] pub url: String,
    #[pyo3(get)] pub source: String,
    #[pyo3(get)] pub published_at: Option<String>,  // ISO 8601
    #[pyo3(get)] pub matched_keywords: Vec<String>,
    #[pyo3(get)] pub snippet: Option<String>,
}

pub struct FeedConfig {
    pub url: String,
    pub feed_type: FeedType,  // Rss | JsonApi
    pub name: String,
}

pub enum FeedType { Rss, JsonApi { api_key_env: String } }

// python.rs
#[pyclass]
pub struct NewsClient { /* internal state */ }

#[pymethods]
impl NewsClient {
    #[new]
    fn new(
        feeds: Vec<(String, String, String)>,  // (url, type, name) tuples
        user_agent: String,
        rate_limit_secs: f64,
    ) -> PyResult<Self>;

    /// Blocking fetch with keyword filtering.
    fn fetch(&self, keywords: Vec<String>, max_results: usize) -> PyResult<Vec<NewsItem>>;

    /// Async fetch (returns awaitable).
    fn fetch_async<'py>(&self, py: Python<'py>, keywords: Vec<String>, max_results: usize) -> PyResult<Bound<'py, PyAny>>;
}
```

## Dependencies (Cargo.toml)

```toml
[dependencies]
pyo3 = { version = "0.23", features = ["extension-module"] }
pyo3-async-runtimes = { version = "0.23", features = ["tokio-runtime"] }
feed-rs = "2.3"         # RSS/Atom/JSON Feed parsing — replaces custom XML parsing
reqwest = { version = "0.12", default-features = false, features = ["json", "rustls-tls"] }
tokio = { version = "1", features = ["rt-multi-thread", "time", "sync"] }
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
regex = "1.10"
chrono = "0.4"
```

## Implementation Steps

1. **Scaffold the crate.** Boilerplate from `crates/efts/`.

2. **Implement `models.rs`.** Define `NewsItem`, `FeedConfig`, `FeedType`. Derive `Serialize` and `#[pyclass]` on `NewsItem`.

3. **Implement `http.rs`.** Async reqwest client with configurable rate limit delay between requests (use `tokio::time::sleep`). Retry logic (copy pattern from `crates/efts/src/http.rs`). Accept `User-Agent` header.

4. **Implement RSS parser** (`feeds/rss.rs`). Use `quick-xml` to parse `<channel><item>` elements. Extract `<title>`, `<link>`, `<pubDate>`, `<description>`. Parse dates to ISO 8601 using `chrono`.

5. **Implement JSON API adapter** (`feeds/json_api.rs`). Handle NewsAPI format (`articles[].title`, `.url`, `.publishedAt`, `.description`). Support API key via environment variable. Polygon format as a second variant.

6. **Implement keyword filter** (`filter.rs`). Compile keyword list into a `regex::RegexSet` (case-insensitive). For each `NewsItem`, check title + snippet against the set. Populate `matched_keywords` with the matching terms.

7. **Implement deduplication** (`dedup.rs`). SimHash on lowercased title tokens (reuse the concept from `crates/efts/src/ranking.rs`). Configurable Hamming distance threshold (default 3). Filter out near-duplicate headlines.

8. **Implement `client.rs`.** Orchestrate: iterate feeds → fetch → parse → filter → dedupe → return sorted by `published_at` descending. Cap at `max_results`.

9. **Implement `python.rs`.** `NewsClient` PyO3 class with `fetch()` (blocking) and `fetch_async()` (uses `pyo3-async-runtimes`). Register in `lib.rs`.

10. **Add to root Makefile.** `NEWSWATCH_DIR`, `NEWSWATCH_MANIFEST`, `rs-nw-%` target, include in `build-ext`.

11. **Write Python wrapper** (`src/sec_nlp/core/news/client.py`). Lazy-import pattern. `NewsRetriever` class wrapping the Rust `NewsClient`. Convert `NewsItem` to Pydantic models.

12. **Add type stubs** (`types/newswatch/__init__.pyi`).

13. **Write tests.** Rust: parse fixture RSS/JSON files, filter/dedup unit tests. Python: mock the extension. No real HTTP calls in any test.

## Testing Strategy

- Rust tests load fixture XML/JSON from `tests/fixtures/` and verify parsing output.
- Filter tests use a known keyword set and verify `matched_keywords` population.
- Dedup tests create headlines with minor variations and verify deduplication.
- No network calls in tests — use `test_support` fixtures or mock HTTP responses.
