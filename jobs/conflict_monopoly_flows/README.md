# Conflict And Monopoly Flow Specs

This directory contains two large retrieve->chat flow specs built around:

- the rare earth minerals basket (`rems`)
- the quantum basket (`quantum`)

Each flow uses four retrieve stages before the final chat stage:

- `retrieve_simple_terms` for short, broad lexical terms
- `retrieve_conflict_terms` for geopolitical conflict and sanctions language
- `retrieve_monopoly_terms` for concentration, exclusivity, and monopoly language
- `retrieve_complex_terms` for longer synthesis-style filing queries

The final `chat` stage does not consume `seed_context`. Instead, each retrieve
stage indexes into one shared Qdrant collection so the answer stage can search
the full accumulated filing set.

Date window:

- `start_date` is fixed to `2023-03-12`
- `end_date` is omitted so the effective upper bound is the day the job runs

## Usage

Validate one spec:

```bash
uv run sec-nlp flow validate --spec jobs/conflict_monopoly_flows/01_rems_conflict_monopoly_large.yaml
```

Run one spec:

```bash
uv run sec-nlp flow run --spec jobs/conflict_monopoly_flows/01_rems_conflict_monopoly_large.yaml
```

Run both specs:

```bash
for spec in jobs/conflict_monopoly_flows/*.yaml; do
  uv run sec-nlp flow run --spec "$spec"
done
```

Notes:

- Replace `you@example.com` before execution.
- These specs target Docker Qdrant at `http://localhost:6333`.
- Each retrieve stage keeps `top_k <= 180` and `efts_candidates <= 1000`.
- The conflict, monopoly, and complex stages intentionally use short lexical
  phrases rather than narrative prompts because EFTS ranks filing language more
  reliably with compact query terms.

## Benchmark Candidates

Useful comparison flows for retrieval-quality and latency checks:

- `jobs/model_variety_flows/03_rems_high_qwen.yaml`
- `jobs/model_variety_flows/05_quantum_high_qwen_ministral.yaml`
- `jobs/merged_basket_high_models/05_rems_large.yaml`
- `jobs/merged_basket_high_models/11_quantum_large.yaml`

Useful perf-suite cases after the updates in `src/scripts/profile/perf_suite.py`:

```bash
uv run python src/scripts/profile/perf_suite.py \
  --include-cases retrieve_rems_thematic \
  --include-cases chat_rems_thematic \
  --include-cases retrieve_quantum_thematic \
  --include-cases chat_quantum_thematic
```

Useful end-to-end flow benchmark cases:

```bash
uv run python src/scripts/profile/perf_suite.py \
  --include-cases flow_rems_conflict_monopoly_large \
  --include-cases flow_rems_high_qwen \
  --include-cases flow_rems_large_merged \
  --include-cases flow_quantum_conflict_monopoly_large \
  --include-cases flow_quantum_high_qwen_ministral \
  --include-cases flow_quantum_large_merged
```

Benchmark interpretation note:

- The baseline candidate flows differ in date window, symbol basket, and prompt
  shape, so treat those runs as directional latency and retrieval baselines.
- If you want strict apples-to-apples comparisons, clone the baseline specs and
  align symbols, forms, and `start_date` to the `2023-03-12` to run-date window
  used by these conflict and monopoly flows.
