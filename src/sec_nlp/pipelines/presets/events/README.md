# Events Pipeline

`events` detects material events from current reports and scores market impact.

## Command

```bash
sec-nlp research events AAPL --event-types merger restatement
```

## Core Flow

1. Scan 8-K/6-K filings for event candidates.
2. Optionally enrich events with surrounding headlines.
3. Optionally run event-study scoring against a benchmark.
4. Emit timeline and summary outputs.

## Key Configuration

- Env prefix: `SEC_NLP_EVENTS_`
- Supported mode/forms: current filings only (`8-K`, `6-K`)
- `lookback_years`, `limit`, `event_types`
- Event-study windows: `pre_window_days`, `post_window_days`
- Context toggles: `include_news_context`, `include_market_context`
- `significance_threshold`, `benchmark_symbol`

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
outputs/<run_timestamp>/events/<SYMBOL>/
```

Files:
- `<symbol>_events_<run_id>_timeline.csv`
- `<symbol>_events_<run_id>_summary.json`
- `<symbol>_events_<run_id>_summary.yaml`

Default `output_format` is `json`.

## Source Pointers

- Config: `src/sec_nlp/pipelines/presets/events/config.py`
- Pipeline: `src/sec_nlp/pipelines/presets/events/pipeline.py`
- Steps: `src/sec_nlp/pipelines/presets/events/steps/`
