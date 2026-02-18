# Architecture Overview

`sec-nlp` is a Python-first orchestration system with Rust extensions for performance-critical integration points (EFTS and market data). It supports both LLM-driven and deterministic SEC/market workflows behind one CLI.

## Code Layout
- `src/sec_nlp/cli/` - command models, argument normalization, and command dispatch.
- `src/sec_nlp/pipelines/base/` - shared pipeline lifecycle, config, validation, and result models.
- `src/sec_nlp/pipelines/presets/` - production pipeline implementations (`analyze`, `exb`, `warranty`, `financials`, `holdings`, `insider`, `news`, `events`, `retrieve`, `chat`).
- `src/sec_nlp/core/` - EDGAR ingestion, text processing, stats, market/news helpers, and infra services.
- `src/sec_nlp/pipelines/observability/` - run registry + metrics/profiling.
- `crates/` - Rust crates (`efts`, `market`, `xbrl`, `corr`, `entity`, `newswatch`).

## Runtime Layers
1. CLI layer: parses/normalizes args and instantiates command config.
2. Pipeline config layer: immutable Pydantic settings merged from CLI/env/.env.
3. Pipeline execution layer: per-symbol phase execution with run metadata.
4. IO/export layer: run-scoped artifacts written in CSV/JSON/YAML.
5. Observability layer: run registry (SQLite) + optional metrics/tracing.

## Pipeline Families
- LLM-centric: `analyze`, `chat`
- Retrieval/indexing: `retrieve`, `exb`
- Deterministic SEC extraction: `warranty`, `financials`, `holdings`, `insider`
- Timeline/correlation: `news`, `events`

## Analyze Flow
1. Load filings (optionally with EFTS expansion).
2. Chunk/filter/dedupe content.
3. Optional vector indexing/search retrieval.
4. LLM analysis for retrieved chunks.
5. Aggregate, enrich (market correlation optional), and export.

Reference: `docs/pipelines/analyze/README.md`

## Deterministic Pipeline Pattern
Most non-LLM presets follow:
1. Download filings or external source records.
2. Parse/normalize structured entities.
3. Compute diffs, clusters, correlations, or timeline rollups.
4. Export symbol-scoped run artifacts.

## Output Conventions
All pipelines use run-scoped output roots:

```text
outputs/<run_timestamp>/<pipeline_type>/<SYMBOL>/...
```

File names usually include `<run_id>` and pipeline-specific suffixes (for example: `_summary`, `_timeline`, `_ledger`, `_snapshot`, `_ranked`).

Analyze keeps per-accession directories:

```text
outputs/<run_timestamp>/analyze/<SYMBOL>/<accession>/analysis.{yaml,json,csv}
outputs/<run_timestamp>/analyze/<SYMBOL>/search/summary.yaml
```

## Run Registry
- SQLite registry path: `.cache/sec-nlp/runs.db`
- Tracks run id, short id, pipeline type, status, timestamps, and metadata
- Managed via `sec-nlp runs ...`

## Design Priorities
- Repeatable run-scoped outputs with provenance fields.
- Clear separation between config, execution, and serialization.
- Fast-path native integrations through Rust extensions.
- Optional infrastructure dependencies (Qdrant, Docker) instead of mandatory services.
