# Benchmark Matrix Flows

These specs shadow the REM and quantum baseline candidates used in
`src/scripts/profile/perf_suite.py` and the branch report workflow.

They intentionally normalize only the comparison-critical dimensions:

- `start_date: '2023-03-12'`
- the same symbol baskets/forms as the corresponding conflict-monopoly flows
- `llm_timeout_seconds: 360` on answer stages
- dedicated benchmark collection names

They preserve the source candidate query families, prompt shape, and model
selection so the benchmark remains a comparison of candidate approaches rather
than a single homogenized flow template.
