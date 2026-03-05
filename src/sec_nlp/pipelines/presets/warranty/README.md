# Warranty Pipeline

`warranty` extracts warranty liability/payout/revenue records from 10-K XBRL content.

## Command

```bash
sec-nlp warranty AAPL
```

## Core Flow

1. Download annual filings (10-K).
2. Load filing XBRL facts.
3. Aggregate and deduplicate period-level warranty records.
4. Write per-filing JSON and symbol-level combined CSV.

## Key Configuration

- Env prefix: `SEC_NLP_WARRANTY_`
- Supported mode: annual only (`10-K`)
- `limit` (filings per symbol)
- `use_item_8_filter` and item filter tuning fields
- `combined_csv` (optional explicit target path)
- `export_format` (`json`, `csv`, `both`; default `both`)

## Shared Semantic Chunking

All presets expose `semantic_chunking.*` nested settings from `BasePipelineSettings`.

Common CLI overrides:
- `--semantic-chunking.enabled true`
- `--semantic-chunking.embedding-model qwen3-embedding:4b`
- `--semantic-chunking.breakpoint-threshold-type gradient`

Pipelines that chunk filing text directly (`retrieve`, `exb`, `warranty`, and loader-backed `analyze`) apply these settings during chunk generation. Other presets keep the same config surface for CLI/flow consistency.

## Outputs

```text
outputs/<run_timestamp>/warranty/<SYMBOL>/
```

Files:
- `<symbol>_warranty_<accession>_<run_id>.json`
- `<symbol>_warranty_combined_<run_id>.csv`

## Source Pointers

- Config: `src/sec_nlp/pipelines/presets/warranty/config.py`
- Pipeline: `src/sec_nlp/pipelines/presets/warranty/pipeline.py`
- Steps: `src/sec_nlp/pipelines/presets/warranty/steps/`
