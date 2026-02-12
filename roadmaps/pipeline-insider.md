# pipeline: `insider` — Insider Trading Pipeline

## Purpose

Build a full pipeline for insider transaction analysis on top of the existing `insider_parser.py`. Aggregate transactions per officer, cross-reference with filing dates and price movement, and flag unusual clusters.

## Existing Implementations — Build vs. Reuse

**`edgartools`** (PyPI) provides Form 4 parsing with `form4_filing.obj()` returning structured transaction data including derivative and non-derivative transactions, ownership changes, and officer details. It handles the full Form 4 XML schema.

**`openinsider`** scrapers (various GitHub repos) pull data from openinsider.com, which aggregates Form 4 data. Fragile HTML scraping, not suitable for production.

**`sec-api`** (PyPI) provides a Form 4 API endpoint with structured JSON output. Requires paid API key.

**Recommendation: Use the existing `insider_parser.py` already in this project.** The parser is already implemented and tested within sec-nlp. No need to introduce `edgartools` just for Form 4 parsing — it would conflict with our download/filing model layer. The pipeline adds orchestration (download → parse → aggregate → correlate → output) on top of the existing parser.

## Existing Code to Study

- `src/sec_nlp/core/edgar/insider_parser.py` — existing `InsiderParser` class.
- `src/sec_nlp/pipelines/presets/warranty/` — reference pipeline structure.
- `src/sec_nlp/core/market.py` — market data for correlation.

## File Structure

```
src/sec_nlp/pipelines/presets/insider/
├── __init__.py
├── config.py           # InsiderSettings(BasePipelineSettings)
├── models.py           # InsiderTransaction, InsiderLedger, InsiderAlert
├── pipeline.py         # InsiderPipeline(BasePipeline)
├── steps/
│   ├── __init__.py
│   ├── download.py     # Fetch Forms 3, 4, 5 for symbol
│   ├── parse.py        # Call existing InsiderParser
│   ├── aggregate.py    # Per-insider ledger, net buys/sells, clustering
│   └── correlate.py    # Cross-ref with filing dates and price movement
└── io/
    ├── __init__.py
    └── formats/
        ├── __init__.py
        ├── ledger.py    # CSV transaction ledger
        └── alerts.py    # YAML/JSON alert list
```

## Pipeline Steps

### 1. `download`
Fetch Forms 3, 4, 5 for the target symbol using existing download infrastructure. Accept `--lookback 12m` to control date range.

### 2. `parse`
Call `InsiderParser` on each downloaded filing. Extract transactions: reporting person, relationship (officer/director/10% owner), transaction type (buy/sell/grant), shares, price, date, post-transaction holdings.

### 3. `aggregate`
Build per-insider transaction ledger. Compute:
- Net buys/sells per officer over the lookback period.
- Transaction clusters: multiple insiders trading within N days of each other.
- Aggregate insider sentiment: net buy ratio = (total buys - total sells) / total transactions.

### 4. `correlate`
Cross-reference insider transaction dates with:
- Filing dates (8-K, 10-K, 10-Q) — flag trades within N days before material filings.
- Price movement via `crates/corr` — compute abnormal returns around transaction dates.
- Volume spikes via `sec_nlp.core.market`.

Flag alerts when: multiple officers sell before an 8-K, large single transaction exceeds threshold, or trades cluster near earnings dates.

### 5. `output`
- Transaction ledger (CSV): one row per transaction, all fields.
- Insider summary (YAML/JSON): per-insider aggregates.
- Alert list: flagged items with reason codes.

## Config (Pydantic)

```python
class InsiderSettings(BasePipelineSettings):
    model_config = SettingsConfigDict(env_prefix="SEC_NLP_INSIDER_")
    symbol: str
    lookback_months: int = 12
    alert_cluster_threshold: int = 3   # N insiders trading in same window
    alert_window_days: int = 5         # Window size for cluster detection
    output_format: str = "csv"
```

## CLI Command

```
sec-nlp insider AAPL --lookback 12m --alert-threshold 3
```

## Implementation Steps

1. Create `insider/` directory with boilerplate.
2. Implement Pydantic models: `InsiderTransaction`, `InsiderLedger`, `InsiderAlert` (frozen, extra="forbid").
3. Implement `download.py` — fetch Form 3/4/5 filings.
4. Implement `parse.py` — call existing `InsiderParser`, map to Pydantic models.
5. Implement `aggregate.py` — per-insider ledger, cluster detection.
6. Implement `correlate.py` — cross-ref with filings and market data.
7. Implement output formatters.
8. Add CLI command, register in `root.py`.
9. Write tests: mock parser output, verify aggregation and alerting logic. No network.

## Dependencies

- Existing `insider_parser.py`
- `crates/corr` (via `sec_nlp.core.stats.correlation`)
- `sec_nlp.core.market` (existing)
- No new PyPI dependencies
