# Conflict/Monopoly Benchmark Reports

This directory stores the curated benchmark evidence for the conflict/monopoly
feature branch. Raw timestamped run artifacts stay local under
`logs/perf/branch_report/` and are not committed.

## Contents

- `feature_summary.json`: stable summary for the current feature branch `HEAD`
- `main_summary.json`: stable summary for the local `main` baseline
- `comparison_summary.json`: per-case deltas between feature and baseline
- `report.md`: Markdown report for review before merge

## Prerequisites

- local `main` is up to date enough to serve as the comparison baseline
- `uv` environment is installed and working in both the feature checkout and
  the temporary `main` worktree
- local Ollama is available for chat and flow benchmark cases
- filing retrieval access is available for SEC benchmark runs
- local Qdrant access is available; the workflow writes suite-specific local
  data under `.qdrant/branch_report/`

## Refresh

Run the full `HEAD` vs local `main` report workflow:

```bash
make -C src benchmark-report BENCHMARK_EMAIL=you@example.com
```

Rebuild the stable summaries from existing raw artifacts:

```bash
make -C src benchmark-summaries BENCHMARK_EMAIL=you@example.com
```

Run the raw perf suite directly by tags:

```bash
uv run python3 src/scripts/profile/perf_suite.py \
  --include_tags thematic \
  --include_tags benchmark
```

## Interpretation

- The thematic retrieve/chat suite is directional. It is useful for latency and
  retrieval sanity checks, but it is not a like-for-like flow comparison.
- The aligned shadow specs under `jobs/benchmark_matrix_flows/` are the fair
  baseline inputs for REM and quantum flow comparisons.
- `flow_overhead` is preserved in the stable summaries so setup and warmup
  costs remain visible instead of disappearing into stage-only timing totals.
