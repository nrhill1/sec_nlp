# pipeline: `events` — Event Detection & Timeline Pipeline

## Purpose

Detect material corporate events from filings and news, then assemble a chronological event timeline with market impact analysis. Combines `crates/entity` (event phrase detection), `crates/newswatch`, and `crates/corr` (event study).

## Existing Implementations — Build vs. Reuse

**No single existing library covers this end-to-end.** Event detection on SEC filings is a niche application. Some related tools:

**`edgartools`** (PyPI) can retrieve 8-K filings and their item numbers (which indicate event types per SEC taxonomy), but does not perform NLP-based event detection or market impact analysis.

**`sec-api`** (PyPI) provides 8-K item classification. SaaS API, not local.

**Academic event study tools** (`eventstudy` PyPI package, `eventstudies` R package) provide statistical frameworks for event studies but don't handle filing retrieval or event detection.

**Recommendation: Custom pipeline composing existing sec-nlp crates.** This pipeline is a composition layer — it doesn't need new core logic, just orchestration of `crates/entity` (event phrase extraction), `crates/newswatch` (surrounding news), and `crates/corr` (event study statistics). The 8-K item number can be used as a coarse event classifier, with `crates/entity` refining the classification from the filing text.

## File Structure

```
src/sec_nlp/pipelines/presets/events/
├── __init__.py
├── config.py           # EventsSettings(BasePipelineSettings)
├── models.py           # DetectedEvent, EventTimeline, EventImpact
├── pipeline.py         # EventsPipeline(BasePipeline)
├── steps/
│   ├── __init__.py
│   ├── scan.py         # Pull 8-K filings, detect event phrases
│   ├── enrich.py       # Add surrounding news and market data
│   └── score.py        # Run event-study analysis per event
└── io/
    ├── __init__.py
    └── formats/
        ├── __init__.py
        └── timeline.py  # Chronological event timeline output
```

## Pipeline Steps

### 1. `scan`
Pull 8-K filings (current reports) for the target symbol within the lookback period. For each filing:
- Extract the 8-K item number(s) from the filing index (coarse classification: 1.01 = material agreement, 2.01 = acquisition/disposition, 5.02 = departure of directors, etc.).
- Apply `crates/entity` event phrase detection on the filing text to refine the event type and extract specific details (e.g., "merger with CompanyX", "restatement of Q3 2024 revenue").
- Emit `DetectedEvent` with: event_type, date, filing_accession, 8k_items, entity_mentions, raw_text_snippet.

### 2. `enrich`
For each detected event:
- Pull surrounding news via `crates/newswatch` (±3 days around event date, filtered by company name/ticker).
- Fetch market data via `sec_nlp.core.market` (price, volume for ±30 day window).
- Attach headline matches and price snapshot to the event.

### 3. `score`
Run event-study analysis using `crates/corr`:
- Compute cumulative abnormal returns (CAR) for 5-day and 30-day windows post-event.
- Compute volume spike ratio (event-day volume / 20-day average volume).
- Run t-test on pre/post returns for statistical significance.
- Attach `EventImpact` with: car_5d, car_30d, volume_spike, t_stat, p_value.

### 4. `output`
Chronological event timeline (JSON/YAML) with per-event fields: event_type, date, filing_accession, headline_matches, car_5d, car_30d, volume_spike, significance.

## Config (Pydantic)

```python
class EventsSettings(BasePipelineSettings):
    model_config = SettingsConfigDict(env_prefix="SEC_NLP_EVENTS_")
    symbol: str
    lookback_years: int = 2
    event_types: list[str] = []   # Filter: "merger", "restatement", "executive", etc.
    pre_window_days: int = 5
    post_window_days: int = 30
    output_format: str = "json"
```

## CLI Command

```
sec-nlp events AAPL --lookback 2y --event-types merger restatement executive
```

## Implementation Steps

- [x] Create `events/` directory with boilerplate.
- [x] Implement Pydantic models: `DetectedEvent`, `EventTimeline`, `EventImpact` (frozen, extra="forbid").
- [x] Implement `scan.py` — fetch 8-K filings, extract item numbers, call entity tagger.
- [x] Implement `enrich.py` — call newswatch wrapper, fetch market data.
- [x] Implement `score.py` — call corr event_study, compute CAR and volume spikes.
- [x] Implement timeline output formatter.
- [x] Add CLI command, register in `root.py`.
- [x] Write tests: mock entity tagger, newswatch, market data. Verify event classification and scoring with deterministic data. No network.

## Dependencies

- `crates/entity` (via `sec_nlp.core.text.entity_extraction`)
- `crates/newswatch` (via `sec_nlp.core.news.client`)
- `crates/corr` (via `sec_nlp.core.stats.correlation`)
- `sec_nlp.core.market` (existing)
- Existing download/ingest infrastructure
