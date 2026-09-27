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

## Shared Semantic Chunking

All presets expose `semantic_chunking.*` nested settings from `BasePipelineSettings`.
Semantic chunking defaults to disabled; explicitly enable it only with the `vector`
extra and an available embedding model. Local sentence/section chunking requires no AI service.

Common CLI overrides:
- `--semantic-chunking.enabled true`
- `--semantic-chunking.embedding-model qwen3-embedding:4b`
- `--semantic-chunking.breakpoint-threshold-type gradient`

Pipelines that chunk filing text directly (`retrieve`, `exb`, `warranty`, and loader-backed `analyze`) apply these settings during chunk generation. Other presets keep the same config surface for research configuration consistency.

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
