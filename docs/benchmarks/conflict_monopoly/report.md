# Conflict/Monopoly Benchmark Report

- Generated at: `2026-03-14T01:33:38.780503+00:00`
- Feature branch: `benchmarks-runtime-offline` at `a1fc437d942acf902e8dcf6391e2e3ec5f4df262`
- Baseline ref: `5dadf05a96dfc94456e142e962d111b93c6fb81a` at `5dadf05a96dfc94456e142e962d111b93c6fb81a`
- Stable JSON summaries: [feature_summary.json](feature_summary.json), [baseline_summary.json](baseline_summary.json), [comparison_summary.json](comparison_summary.json)

## Environment assumptions

- Local Ollama is available for chat/flow cases.
- Local Qdrant is available at `http://localhost:6333` for flow suites.
- Raw run artifacts are local-only under `logs/perf/branch_report/` and are not committed.

## Suite configuration

- `thematic_retrieve_chat`: repeats=2; Directional retrieve/chat cases for REM and quantum baskets.
- `flow_rems_candidates`: repeats=1; Aligned REM flow comparisons across conflict, merged, and model-variety candidates.
- `flow_quantum_candidates`: repeats=1; Aligned quantum flow comparisons across conflict, merged, and model-variety candidates.

## Caveats

- Thematic retrieve/chat suites are directional latency and retrieval checks rather than full flow comparisons.
- Flow baseline shadow specs align date windows, baskets, timeout policy, and dedicated collection names with the conflict/monopoly flows.
- Cases without fully successful iterations are marked invalid and render timing deltas as `n/a` instead of treating empty-context runs as real wins.
- `flow_overhead` captures setup and warmup work outside stage `invoke()` timings and is preserved in the JSON summaries.

## thematic_retrieve_chat

Directional retrieve/chat cases for REM and quantum baskets.

| Case | Status | Feature ok/iters | Baseline ok/iters | Feature p95 (s) | Baseline p95 (s) | Delta (s) | Delta (%) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| chat_quantum_thematic | baseline_invalid | 2/2 | 0/2 | 25.983322 | n/a | n/a | n/a |
| chat_rems_thematic | baseline_invalid | 2/2 | 0/2 | 30.365689 | n/a | n/a | n/a |
| retrieve_quantum_thematic | baseline_invalid | 2/2 | 0/2 | 56.588244 | n/a | n/a | n/a |
| retrieve_rems_thematic | baseline_invalid | 2/2 | 0/2 | 66.934532 | n/a | n/a | n/a |

## flow_rems_candidates

Aligned REM flow comparisons across conflict, merged, and model-variety candidates.

| Case | Status | Feature ok/iters | Baseline ok/iters | Feature p95 (s) | Baseline p95 (s) | Delta (s) | Delta (%) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| flow_rems_conflict_monopoly_large | baseline_invalid | 1/1 | 0/1 | 425.626728 | n/a | n/a | n/a |
| flow_rems_high_qwen | baseline_invalid | 1/1 | 0/1 | 108.009011 | n/a | n/a | n/a |
| flow_rems_large_merged | baseline_invalid | 1/1 | 0/1 | 157.797702 | n/a | n/a | n/a |

## flow_quantum_candidates

Aligned quantum flow comparisons across conflict, merged, and model-variety candidates.

| Case | Status | Feature ok/iters | Baseline ok/iters | Feature p95 (s) | Baseline p95 (s) | Delta (s) | Delta (%) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| flow_quantum_conflict_monopoly_large | baseline_invalid | 1/1 | 0/1 | 1781.837273 | n/a | n/a | n/a |
| flow_quantum_high_qwen_ministral | baseline_invalid | 1/1 | 0/1 | 116.957354 | n/a | n/a | n/a |
| flow_quantum_large_merged | baseline_invalid | 1/1 | 0/1 | 150.070006 | n/a | n/a | n/a |
