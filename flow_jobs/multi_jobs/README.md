# Multi-Job Flow Specs

This directory contains 30 retrieve->chat flow specs covering six baskets and five size profiles each:

- `smoke`
- `rems`
- `tech`
- `quantum`
- `biotech`
- `mining`

Profiles:

- `smoke` (quick sanity run)
- `small`
- `medium`
- `large`
- `xlarge`

All specs are designed to maximize hit probability by using broad SEC filing forms, long keyword-rich retrieve queries, and basket-specific symbols.

## Usage

Validate one spec:

```bash
uv run sec-nlp flow validate --spec flow_jobs/multi_jobs/01_smoke_smoke.yaml
```

Run one spec:

```bash
uv run sec-nlp flow run --spec flow_jobs/multi_jobs/01_smoke_smoke.yaml
```

Run all specs:

```bash
for spec in flow_jobs/multi_jobs/*.yaml; do
  uv run sec-nlp flow run --spec "$spec"
done
```

Notes:

- Replace `you@example.com` per file or via flow defaults before running.
- Profiles with `index_results: true` write into Qdrant collection names prefixed with `flow_...`.
- For merged, high-parameter basket collections, use:
  `/Users/nicolashill/Projects/sec/flow_jobs/merged_basket_high_models/README.md`.
