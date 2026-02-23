# Merged Basket High-Model Flow Specs

This directory contains 18 retrieve->chat flow specs with:

- merged Qdrant collection per basket (`basket_<basket>_hq`)
- higher-parameter embedding model (`qwen3-embedding:4b`, `vector_size=2560`)
- higher-parameter chat model (`qwen3:8b`)
- Docker Qdrant target (`http://localhost:6333`)

Baskets covered:

- smoke
- rems
- tech
- quantum
- biotech
- mining

Profiles per basket:

- medium
- large
- xlarge

## Usage

Validate one spec:

```bash
uv run sec-nlp flow validate --spec flow_jobs/merged_basket_high_models/01_smoke_medium.yaml
```

Run one spec:

```bash
uv run sec-nlp flow run --spec flow_jobs/merged_basket_high_models/01_smoke_medium.yaml
```

Run all specs:

```bash
for spec in flow_jobs/merged_basket_high_models/*.yaml; do
  uv run sec-nlp flow run --spec "$spec"
done
```

Notes:

- Update `defaults.email` from `you@example.com` before running.
- For each basket, run medium -> large -> xlarge to incrementally build and reuse the same merged collection.
- `top_k` values remain <= 200.
