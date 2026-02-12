# pipeline: `news` — News Monitoring Pipeline

## Purpose

Monitor financial news sources for keyword matches around a target company, correlate news volume with filing dates and market moves, and produce a timeline view.

## Existing Implementations — Build vs. Reuse

**`finvizfinance`** (PyPI) scrapes Finviz for news, insider trades, and analyst ratings. Fragile (HTML scraping), no RSS support.

**`newsapi-python`** (PyPI) is the official Python client for NewsAPI.org. Requires API key, limited to 100 requests/day on free tier, and only searches recent articles. Useful as one data source but not a complete solution.

**`polygon-api-client`** (PyPI) provides Polygon.io news with ticker-level filtering and pagination. Requires paid API key.

**`feedparser`** (PyPI) is the classic Python RSS/Atom parser. Mature but slow for batch processing and lacks async support.

**Recommendation: Use `crates/newswatch` for the core fetch+filter+dedup layer (which uses `feed-rs` internally).** Python-side `newsapi-python` and `polygon-api-client` can be optional adapters for API sources, but the primary RSS/Atom path runs through the Rust crate for throughput. The pipeline orchestration (correlate, output) stays in Python.

## File Structure

```
src/sec_nlp/pipelines/presets/news/
├── __init__.py
├── config.py           # NewsSettings(BasePipelineSettings)
├── models.py           # NewsItem, NewsTimeline, NewsCorrelation
├── pipeline.py         # NewsPipeline(BasePipeline)
├── steps/
│   ├── __init__.py
│   ├── fetch.py        # Call crates/newswatch via Python wrapper
│   ├── match.py        # Score headlines against topic list using EFTS ranking
│   └── correlate.py    # Align news timestamps with filings + market data
└── io/
    ├── __init__.py
    └── formats/
        ├── __init__.py
        └── timeline.py  # JSON/YAML timeline output
```

## Pipeline Steps

### 1. `fetch`
Call `crates/newswatch` `NewsClient.fetch()` with configured feed URLs, keywords, and date range. Returns `list[NewsItem]` with title, url, source, published_at, matched_keywords, snippet.

### 2. `match`
Score each headline against the user's topic list. Reuse EFTS keyword extractors (`crates/efts` ranking module) for TF-IDF-like relevance scoring. Filter out items below a relevance threshold.

### 3. `correlate`
For each news item, find the nearest filing date (using existing filing metadata) and fetch market data for the surrounding window via `sec_nlp.core.market`. Compute news-volume-to-price-change correlation using `crates/corr`. Identify "news clusters" — multiple headlines within a short window — and flag abnormal volume.

### 4. `output`
Produce a timeline view: `date → headlines + filing events + price snapshot`. Output formats: JSON, YAML, CSV.

## Config (Pydantic)

```python
class NewsSettings(BasePipelineSettings):
    model_config = SettingsConfigDict(env_prefix="SEC_NLP_NEWS_")
    symbol: str
    topics: list[str] = []
    days: int = 90
    feeds: list[str] = []     # Override default RSS feed list
    min_relevance: float = 0.3
    output_format: str = "json"
```

## CLI Command

```
sec-nlp news AAPL --topics "supply chain" recall --days 90
```

## Implementation Steps

1. Create `news/` directory with config, models, pipeline boilerplate.
2. Implement `NewsItem` and `NewsTimeline` Pydantic models.
3. Implement `fetch.py` — call `crates/newswatch` wrapper. Default feed list: SEC RSS, PR Newswire, BusinessWire.
4. Implement `match.py` — relevance scoring against topic keywords.
5. Implement `correlate.py` — align with filings and market data, compute correlation.
6. Implement timeline output formatter.
7. Add CLI command, register in `root.py`.
8. Write tests: mock newswatch crate, mock market data. Verify correlation logic with deterministic timestamps. No network.

## Dependencies

- `crates/newswatch` (via `sec_nlp.core.news.client`)
- `crates/corr` (via `sec_nlp.core.stats.correlation`)
- `sec_nlp.core.market` (existing)
- No new PyPI dependencies (optional: `newsapi-python`, `polygon-api-client` for additional sources)
