# Documentation Index

This directory is organized by scope.

## Root docs (cross-cutting)
- `ARCHITECTURE.md` - system architecture and runtime design
- `PROJECT_STATE.md` - current command/pipeline/output snapshot
- `AGENTS.md` - project-specific contributor/agent rules

## Pipeline docs
- `pipelines/README.md` - index of all pipeline docs
- `pipelines/analyze/README.md` - analyze pipeline walkthrough
- `pipelines/chat/README.md` - retrieval-augmented chat pipeline
- `pipelines/events/README.md` - event detection timeline pipeline
- `pipelines/exb/README.md` - exhibit extraction/index pipeline
- `pipelines/financials/README.md` - financial statement extraction pipeline
- `pipelines/holdings/README.md` - 13F holdings pipeline
- `pipelines/insider/README.md` - insider transaction analysis pipeline
- `pipelines/news/README.md` - news monitoring/correlation pipeline
- `pipelines/retrieve/README.md` - EFTS-first retrieval pipeline
- `pipelines/warranty/README.md` - warranty XBRL pipeline
- `pipelines/analyze/OUTPUTS_ANALYZE.md` - analyze output schema
- `pipelines/analyze/OUTPUTS_SEARCH_SUMMARY.md` - analyze search summary schema
- `pipelines/analyze/EFTS_KEYWORDS_CORRELATION.md` - analyze-specific design notes

## Crate docs
- `crates/README.md` - index of Rust crate docs
- `crates/corr/README.md` - correlation/statistics extension docs
- `crates/efts/README.md` - EFTS Rust extension docs
- `crates/entity/README.md` - entity extraction/tagging extension docs
- `crates/market/README.md` - market Rust extension docs
- `crates/newswatch/README.md` - news ingestion extension docs
- `crates/xbrl/README.md` - XBRL parsing extension docs

## Placement rules
- Put pipeline-specific docs under `docs/pipelines/<pipeline>/`.
- Put Rust extension docs under `docs/crates/<crate>/`.
- Keep only cross-cutting docs at `docs/` root.
