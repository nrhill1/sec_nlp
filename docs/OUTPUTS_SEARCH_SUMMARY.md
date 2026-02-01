# Search Summary Output Schema

This document describes the structure of `search/summary.yaml` produced by the analyze pipeline.

## Location

```
outputs/<run_timestamp>/analyze/<SYMBOL>/search/summary.yaml
```

## Top-level Fields

- `symbol` – The symbol for the summary.
- `score_threshold` – Search score threshold applied.
- `metadata_filters` – Any metadata filters applied.
- `total_queries` – Number of queries in the run.
- `total_unique_results` – De-duplicated results count.
- `queries` – Per-query sections.
  - `query`
  - `results_count`
  - `stats` (avg/best score, sections, tags, sentiment)
  - `highlights`
  - `results`
- `unique_results` – Consolidated hits across all queries.

## Rounding Rules

- **Scores** (match scores, avg/best scores, confidence): rounded to 2 decimals.
