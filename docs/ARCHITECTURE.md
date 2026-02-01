# Architecture Overview

This project blends Python pipeline orchestration with Rust-powered compute (EFTS, market, etc.). The primary goal is to ingest SEC filings, retrieve relevant chunks, and produce structured analyses and summaries at scale.

## High-level Layout

- `src/sec_nlp/` – Python application and pipeline orchestration.
  - `pipelines/` – Shared pipeline infrastructure and presets.
  - `pipelines/presets/analyze/` – Analyze pipeline (EFTS, vector search, LLM analysis, market correlation).
  - `pipelines/metadata/` – Metadata helpers and normalization.
  - `pipelines/output_io.py` – JSON/YAML IO helpers.
  - `pipelines/serialization.py` – Shared rounding + serialization utilities.
- `crates/` – Rust crates for performance-sensitive operations.
- `docs/` – Documentation, pipelines, and output schema references.

## Data Flow (Analyze)

1. **Load filings** from EDGAR (or local cache).
2. **Chunk & preprocess** (filters, topics, dedup).
3. **Vector search** to find relevant chunks.
4. **LLM analysis** on retrieved chunks.
5. **Optional market correlation** on relevant results.
6. **Export outputs** (analysis + search summaries).

See `docs/pipelines/analyze/README.md` for the step-by-step flow.

## Output Layout

Outputs are run-scoped:

```
outputs/<run_timestamp>/<pipeline>/<SYMBOL>/<accession>/analysis.yaml
outputs/<run_timestamp>/<pipeline>/<SYMBOL>/search/summary.yaml
```

See:
- `docs/OUTPUTS_ANALYZE.md`
- `docs/OUTPUTS_SEARCH_SUMMARY.md`

## Serialization & Rounding

All rounding and serialization go through shared helpers in:

```
src/sec_nlp/pipelines/serialization.py
```

This keeps output formatting consistent across JSON/YAML/CSV.

## Key Design Goals

- **Deterministic, reproducible outputs**
- **Memory-aware chunk processing**
- **Centralized formatting/normalization**
- **Well-documented outputs and contracts**
