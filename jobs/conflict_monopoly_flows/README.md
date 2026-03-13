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
