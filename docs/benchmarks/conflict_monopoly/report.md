# Conflict/Monopoly Benchmark Report

- Generated at: `2026-03-13T20:13:40.101772+00:00`
- Feature branch: `benchmarks-runtime-offline` at `b3358b8dd89f38ff4756026961022c4820985edf`
- Baseline branch: `main` at `5dadf05a96dfc94456e142e962d111b93c6fb81a`
- Stable JSON summaries: [feature_summary.json](feature_summary.json), [main_summary.json](main_summary.json), [comparison_summary.json](comparison_summary.json)

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
- `flow_overhead` captures setup and warmup work outside stage `invoke()` timings and is preserved in the JSON summaries.

## thematic_retrieve_chat

Directional retrieve/chat cases for REM and quantum baskets.

| Case | Feature p95 (s) | Main p95 (s) | Delta (s) | Delta (%) |
| --- | ---: | ---: | ---: | ---: |
| chat_quantum_thematic | 7.367029 | 3.528833 | 3.838196 | 108.766723 |
| chat_rems_thematic | 7.809026 | 19.301317 | -11.492291 | -59.541486 |
| retrieve_quantum_thematic | 7.492491 | 3.56423 | 3.928261 | 110.213454 |
| retrieve_rems_thematic | 7.535211 | 170.251047 | -162.715836 | -95.574059 |

## flow_rems_candidates

Aligned REM flow comparisons across conflict, merged, and model-variety candidates.

| Case | Feature p95 (s) | Main p95 (s) | Delta (s) | Delta (%) |
| --- | ---: | ---: | ---: | ---: |
| flow_rems_conflict_monopoly_large | 279.488937 | 10.872464 | 268.616473 | 2470.612669 |
| flow_rems_high_qwen | 109.8009 | 11.548779 | 98.252121 | 850.757652 |
| flow_rems_large_merged | 155.9578 | 7.920634 | 148.037166 | 1869.006521 |

## flow_quantum_candidates

Aligned quantum flow comparisons across conflict, merged, and model-variety candidates.

| Case | Feature p95 (s) | Main p95 (s) | Delta (s) | Delta (%) |
| --- | ---: | ---: | ---: | ---: |
| flow_quantum_conflict_monopoly_large | 986.968316 | 11.624687 | 975.343629 | 8390.278629 |
| flow_quantum_high_qwen_ministral | 119.454062 | 11.357459 | 108.096603 | 951.767495 |
| flow_quantum_large_merged | 153.848326 | 11.357359 | 142.490967 | 1254.613568 |
