# Conflict/Monopoly Benchmark Report

- Generated at: `2026-03-14T05:01:30.695119+00:00`
- Feature branch: `benchmarks-runtime-offline` at `8afab23645034ff66ec809b74fabe574e25f03e6`
- Baseline ref: `8afab23645034ff66ec809b74fabe574e25f03e6` at `8afab23645034ff66ec809b74fabe574e25f03e6`
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
| chat_quantum_thematic | baseline_invalid | 2/2 | 0/2 | 22.2961 | n/a | n/a | n/a |
| chat_rems_thematic | baseline_invalid | 2/2 | 0/2 | 23.693952 | n/a | n/a | n/a |
| retrieve_quantum_thematic | baseline_invalid | 2/2 | 0/2 | 34.81081 | n/a | n/a | n/a |
| retrieve_rems_thematic | baseline_invalid | 2/2 | 0/2 | 41.731579 | n/a | n/a | n/a |

## flow_rems_candidates

Aligned REM flow comparisons across conflict, merged, and model-variety candidates.

| Case | Status | Feature ok/iters | Baseline ok/iters | Feature p95 (s) | Baseline p95 (s) | Delta (s) | Delta (%) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| flow_rems_conflict_monopoly_large | baseline_invalid | 1/1 | 0/1 | 232.875207 | n/a | n/a | n/a |
| flow_rems_high_qwen | baseline_invalid | 1/1 | 0/1 | 117.892434 | n/a | n/a | n/a |
| flow_rems_large_merged | both_invalid | 0/1 | 0/1 | n/a | n/a | n/a | n/a |

## flow_quantum_candidates

Aligned quantum flow comparisons across conflict, merged, and model-variety candidates.

| Case | Status | Feature ok/iters | Baseline ok/iters | Feature p95 (s) | Baseline p95 (s) | Delta (s) | Delta (%) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| flow_quantum_conflict_monopoly_large | baseline_invalid | 1/1 | 0/1 | 260.184593 | n/a | n/a | n/a |
| flow_quantum_high_qwen_ministral | baseline_invalid | 1/1 | 0/1 | 108.350808 | n/a | n/a | n/a |
| flow_quantum_large_merged | baseline_invalid | 1/1 | 0/1 | 149.750865 | n/a | n/a | n/a |
