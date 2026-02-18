# News Pipeline

`news` monitors company-centric headlines and correlates them with filings and returns.

## Command

```bash
sec-nlp news AAPL --topics tariffs supply_chain
```

## Core Flow

1. Fetch headlines from configured/default feeds.
2. Match headlines by topic relevance and symbol rules.
3. Correlate headline activity with filings and market data.
4. Detect headline clusters.
5. Write timeline and summary outputs.

## Key Configuration

- Env prefix: `SEC_NLP_NEWS_`
- `topics`, `days`, `feeds`
- Filtering: `min_relevance`, `require_symbol_match`
- Correlation controls: `include_market_context`, `filing_match_window_days`
- Cluster controls: `cluster_threshold`, `cluster_gap_days`
- `output_format` (default `json`)

## Outputs

```text
outputs/<run_timestamp>/news/<SYMBOL>/
```

Files:
- `<symbol>_news_<run_id>_timeline.csv`
- `<symbol>_news_<run_id>_summary.json`
- `<symbol>_news_<run_id>_summary.yaml`

## Source Pointers

- Config: `src/sec_nlp/pipelines/presets/news/config.py`
- Pipeline: `src/sec_nlp/pipelines/presets/news/pipeline.py`
- Steps: `src/sec_nlp/pipelines/presets/news/steps/`
