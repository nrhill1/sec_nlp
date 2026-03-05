# Insider Pipeline

`insider` analyzes Form 3/4/5 transactions and emits ledger + alert artifacts.

## Command

```bash
sec-nlp insider AAPL --lookback-months 12
```

## Core Flow

1. Download insider filings.
2. Parse insider transactions.
3. Build aggregated ledgers and trade clusters.
4. Correlate activity for alert conditions.
5. Write ledger/summary/alerts outputs.

## Key Configuration

- Env prefix: `SEC_NLP_INSIDER_`
- Supported mode/forms: insider mode only (`3`, `4`, `5`)
- `lookback_months`
- Alert tuning: `alert_cluster_threshold`, `alert_window_days`, `large_trade_threshold_shares`
- `output_format` (default `csv`)

## Shared Semantic Chunking

All presets expose `semantic_chunking.*` nested settings from `BasePipelineSettings`.

Common CLI overrides:
- `--semantic-chunking.enabled true`
- `--semantic-chunking.embedding-model qwen3-embedding:4b`
- `--semantic-chunking.breakpoint-threshold-type gradient`

Pipelines that chunk filing text directly (`retrieve`, `exb`, `warranty`, and loader-backed `analyze`) apply these settings during chunk generation. Other presets keep the same config surface for CLI/flow consistency.

## Outputs

```text
outputs/<run_timestamp>/insider/<SYMBOL>/
```

Files:
- `<symbol>_insider_<run_id>_ledger.csv`
- `<symbol>_insider_<run_id>_summary.json|yaml`
- `<symbol>_insider_<run_id>_alerts.json|yaml`

## Source Pointers

- Config: `src/sec_nlp/pipelines/presets/insider/config.py`
- Pipeline: `src/sec_nlp/pipelines/presets/insider/pipeline.py`
- Steps: `src/sec_nlp/pipelines/presets/insider/steps/`
