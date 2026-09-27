# Financials Pipeline

`financials` extracts normalized statement line items from filing XBRL.

## Command

```bash
sec-nlp research financials AAPL --periods 8
```

## Core Flow

1. Download target filings (`form_types`, default `10-K`/`10-Q`).
2. Extract financial facts from XBRL.
3. Aggregate into normalized period records.
4. Optionally compute ratios and delta report.
5. Write symbol-scoped outputs.

## Key Configuration

- Env prefix: `SEC_NLP_FINANCIALS_`
- `form_types`, `periods`
- `compute_ratios` (default `true`)
- `include_delta_report` (default `false`)
- `output_format` (default `csv`)

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
outputs/<run_timestamp>/financials/<SYMBOL>/
```

Files:
- `<symbol>_financials_<run_id>.csv`
- `<symbol>_financials_<run_id>.json`
- `<symbol>_financials_<run_id>.yaml`

## Source Pointers

- Config: `src/sec_nlp/pipelines/presets/financials/config.py`
- Pipeline: `src/sec_nlp/pipelines/presets/financials/pipeline.py`
- Steps: `src/sec_nlp/pipelines/presets/financials/steps/`
