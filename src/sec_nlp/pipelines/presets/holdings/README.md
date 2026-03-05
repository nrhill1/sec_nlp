# Holdings Pipeline

`holdings` analyzes institutional 13F holdings snapshots and quarter-over-quarter changes.

## Command

```bash
sec-nlp holdings AAPL --quarters 4
```

## Core Flow

1. Download 13F filings.
2. Parse holdings positions.
3. Compute quarter-over-quarter diffs.
4. Build ownership concentration summary.
5. Write snapshot/summary/diff outputs.

## Key Configuration

- Env prefix: `SEC_NLP_HOLDINGS_`
- Supported mode/forms: holdings mode only (`13F-HR`, `13F-HR/A`)
- `quarters`, `top_holders`
- Optional filters: `cusip`, `filer_ciks`
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
outputs/<run_timestamp>/holdings/<SYMBOL>/
```

Files:
- `<symbol>_holdings_<run_id>_snapshot.csv`
- `<symbol>_holdings_<run_id>_summary.json|yaml`
- `<symbol>_holdings_<run_id>_diff.json|yaml`

## Source Pointers

- Config: `src/sec_nlp/pipelines/presets/holdings/config.py`
- Pipeline: `src/sec_nlp/pipelines/presets/holdings/pipeline.py`
- Steps: `src/sec_nlp/pipelines/presets/holdings/steps/`
