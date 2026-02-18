# Documentation Index

This directory is organized by scope.

## Root docs (cross-cutting)
- `ARCHITECTURE.md` - system architecture and runtime design
- `PROJECT_STATE.md` - current command/pipeline/output snapshot
- `AGENTS.md` - project-specific contributor/agent rules

## Pipeline docs
- `pipelines/analyze/README.md` - analyze pipeline walkthrough
- `pipelines/analyze/OUTPUTS_ANALYZE.md` - analyze output schema
- `pipelines/analyze/OUTPUTS_SEARCH_SUMMARY.md` - analyze search summary schema
- `pipelines/analyze/EFTS_KEYWORDS_CORRELATION.md` - analyze-specific design notes

## Crate docs
- `crates/efts/README.md` - EFTS Rust extension docs
- `crates/market/README.md` - market Rust extension docs

## Placement rules
- Put pipeline-specific docs under `docs/pipelines/<pipeline>/`.
- Put Rust extension docs under `docs/crates/<crate>/`.
- Keep only cross-cutting docs at `docs/` root.
