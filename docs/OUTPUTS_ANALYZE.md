# Analyze Output Schema

This document describes the top-level fields in `analysis.yaml` produced by the analyze pipeline.

## Location

```
outputs/<run_timestamp>/analyze/<SYMBOL>/<accession>/analysis.yaml
```

## Top-level Fields

- `symbol` – Ticker symbol used for the run.
- `search_queries` – Queries used to retrieve chunks.
- `filing`
  - `accession_number`
  - `form_type`
  - `acceptance_date`
  - `filing_date`
- `executive_summary`
  - `status`
  - `total_chunks`
  - `relevant_count`
  - `average_confidence`
  - `top_tags`
  - `top_topics`
  - `key_points`
- `aggregates` – Frequency summaries (tags, sentiment, sections, impacts).
- `diagnostics`
  - `chunks_analyzed`
  - `chunks_successful`
  - `chunks_failed`
  - `success_rate`
  - `relevant_rate`
  - `timings` (rounded to 3 decimals)
  - `confidence_threshold`
- `provenance`
  - `run_id`
  - `pipeline_version`
  - `model_name`
  - `confidence_mode`
  - `prompt_path`
  - `prompt_version`
  - `schema_version`
- `market_enrichment` – Aggregated price/volume window (if enabled).
- `market_correlation` – Correlation metrics (if enabled).
- `results` – Ranked list of relevant chunk analyses.
- `results_by_query` – Grouped results by query.
- `results_by_section` – Grouped results by section.
- `relationship_timeline` – Related filings grouped by relation type.

## Rounding Rules

- **Scores** (confidence, overlaps, search scores): rounded to 2 decimals.
- **Timings**: rounded to 3 decimals.
