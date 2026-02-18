# Financials Pipeline

`financials` extracts normalized statement line items from filing XBRL.

## Command

```bash
sec-nlp financials AAPL --periods 8
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
