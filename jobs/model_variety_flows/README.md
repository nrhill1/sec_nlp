# Model Variety Flow Jobs

These flow specs run `retrieve -> chat` with different Ollama embedding/LLM model combinations.
Each chat stage uses investment-strategy prompts with max-output settings (`generation_token_cap: 0`, `llm.max_new_tokens: 8192`).

Files:

- `01_rems_low_granite_llama.yaml`
- `02_rems_medium_mxbai_ministral.yaml`
- `03_rems_high_qwen.yaml`
- `04_tech_medium_mxbai_qwen8b.yaml`
- `05_quantum_high_qwen_ministral.yaml`
- `06_biotech_low_granite_ministral.yaml`

Run all specs in sequence:

```bash
set -euo pipefail
for spec in jobs/model_variety_flows/*.yaml; do
  echo "==> Running $spec"
  uv run sec-nlp flow validate --spec "$spec"
  uv run sec-nlp flow run --spec "$spec"
done
```

Notes:

- All specs default to Docker Qdrant at `http://localhost:6333`.
- Replace `you@example.com` with your SEC contact email.
