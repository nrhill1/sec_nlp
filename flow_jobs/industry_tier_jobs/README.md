# Industry Tier Job Presets

This directory adds 20 preset jobs spanning retrieve-only, chat-only, and
retrieve->chat flow execution.

## Goals

- Consolidate basket data into consistent industry collections.
- Separate each industry into model tiers: low, medium, high.
- Keep topic coverage broad across REMs, tech, quantum, biotech, and mining.

## Tier Model Matrix

- low:
  - embedding: `granite-embedding:30m` (384d)
  - llm: `llama3.2:1b`
- medium:
  - embedding: `mxbai-embed-large:latest` (1024d)
  - llm: `ministral-3:3b`
- high:
  - embedding: `qwen3-embedding:4b` (2560d)
  - llm: `qwen3:8b`

Collection convention:

- `industry_<industry>_<tier>`

Examples:

- `industry_rems_low`
- `industry_tech_medium`
- `industry_mining_high`

## Job Mix

- 15 flow jobs: 5 industries x 3 tiers (`flow`)
- 3 retrieve-only jobs (`retrieve`)
- 2 chat-only jobs (`chat`)

## Usage

Validate all:

```bash
for spec in flow_jobs/industry_tier_jobs/*.yaml; do
  .venv/bin/sec-nlp flow validate --spec "$spec"
done
```

Run one:

```bash
.venv/bin/sec-nlp flow run --spec flow_jobs/industry_tier_jobs/01_flow_rems_low.yaml
```

Run all flow jobs first, then standalone chat/retrieve jobs:

```bash
for spec in flow_jobs/industry_tier_jobs/*_flow_*.yaml; do
  .venv/bin/sec-nlp flow run --spec "$spec"
done
for spec in flow_jobs/industry_tier_jobs/*_retrieve_*.yaml flow_jobs/industry_tier_jobs/*_chat_*.yaml; do
  .venv/bin/sec-nlp flow run --spec "$spec"
done
```

Notes:

- Replace `you@example.com` before execution.
- These presets target Docker Qdrant at `http://localhost:6333`.
- `top_k` remains <= 200 in all jobs.
