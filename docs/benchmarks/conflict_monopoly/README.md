# Conflict/Monopoly Benchmark Reports

This directory stores the curated benchmark evidence for the conflict/monopoly
feature branch. Raw timestamped run artifacts stay local under
`logs/perf/branch_report/` and are not committed.

## Contents

- `feature_summary.json`: stable summary for the current feature branch `HEAD`
- `baseline_summary.json`: stable summary for the configured baseline ref
- `main_summary.json`: legacy alias of `baseline_summary.json` kept for older links
- `comparison_summary.json`: per-case deltas between feature and baseline
- `report.md`: Markdown report for review before merge

## Prerequisites

- a local baseline ref is available for comparison
- `uv` environment is installed and working in both the feature checkout and
  the temporary baseline worktree
- local Ollama is available for chat and flow benchmark cases
- filing retrieval access is available for SEC benchmark runs
- local Qdrant access is available; the workflow writes suite-specific local
  data under `.qdrant/branch_report/`

Pinned commit SHAs are preferred for performance baselines. A moving branch such
as `dev/improvements-v2` is acceptable while iterating, but the committed
report should normally be refreshed against a fixed commit.

## Refresh

Run the full `HEAD` vs baseline report workflow:

```bash
make -C src benchmark-report \
  BENCHMARK_EMAIL=you@example.com \
  BENCHMARK_BASELINE_REF=8afab23645034ff66ec809b74fabe574e25f03e6
```

Rebuild the stable summaries from existing raw artifacts:

```bash
make -C src benchmark-summaries \
  BENCHMARK_EMAIL=you@example.com \
  BENCHMARK_BASELINE_REF=8afab23645034ff66ec809b74fabe574e25f03e6
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
- The default make target baseline is `main`, but performance reporting is more
  stable when `BENCHMARK_BASELINE_REF` is pinned to a commit SHA.
- `flow_overhead` is preserved in the stable summaries so setup and warmup
  costs remain visible instead of disappearing into stage-only timing totals.
