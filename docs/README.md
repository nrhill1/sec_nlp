# Documentation Index

This directory is organized by scope.

## Root docs (cross-cutting)

- `ARCHITECTURE.md` - system architecture and runtime design
- `PROJECT_STATE.md` - retained specialist output conventions
- `MIGRATION.md` - command, import, cache, and authored-job migration map
- `VALIDATION.md` - consolidation measurements and verification evidence
- `PULSE.md` - Pulse market briefs, current-events sources, and local research journal

## Pipeline docs

- `../src/sec_nlp/pipelines/presets/README.md` - index of all pipeline docs
- `../src/sec_nlp/pipelines/presets/analyze/README.md` - analyze pipeline walkthrough
- `../src/sec_nlp/pipelines/presets/chat/README.md` - retrieval-augmented chat pipeline
- `../src/sec_nlp/pipelines/presets/events/README.md` - event detection timeline pipeline
- `../src/sec_nlp/pipelines/presets/exb/README.md` - exhibit extraction/index pipeline
- `../src/sec_nlp/pipelines/presets/financials/README.md` - financial statement extraction pipeline
- `../src/sec_nlp/pipelines/presets/holdings/README.md` - 13F holdings pipeline
- `../src/sec_nlp/pipelines/presets/insider/README.md` - insider transaction analysis pipeline
- `../src/sec_nlp/pipelines/presets/news/README.md` - news monitoring/correlation pipeline
- `../src/sec_nlp/pipelines/presets/retrieve/README.md` - EFTS-first retrieval pipeline
- `../src/sec_nlp/pipelines/presets/warranty/README.md` - warranty XBRL pipeline
- `../src/sec_nlp/pipelines/presets/analyze/OUTPUTS_ANALYZE.md` - analyze output schema
- `../src/sec_nlp/pipelines/presets/analyze/OUTPUTS_SEARCH_SUMMARY.md` - analyze search summary schema
- `../src/sec_nlp/pipelines/presets/analyze/EFTS_KEYWORDS_CORRELATION.md` - analyze-specific design notes

## Crate docs

- `../crates/README.md` - index of Rust crate docs
- `../crates/corr/README.md` - correlation/statistics extension docs
- `../crates/efts/README.md` - EFTS Rust extension docs
- `../crates/entity/README.md` - entity extraction/tagging extension docs
- `../crates/market/README.md` - market Rust extension docs
- `../crates/newswatch/README.md` - news ingestion extension docs
- `../crates/xbrl/README.md` - XBRL parsing extension docs

## Placement rules

- Put pipeline-specific docs under `src/sec_nlp/pipelines/presets/<pipeline>/`.
- Put Rust extension docs under `crates/<crate>/`.
- Keep only cross-cutting/index docs at `docs/` root.
