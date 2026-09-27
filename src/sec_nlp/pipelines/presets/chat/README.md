# Chat Pipeline

`chat` provides retrieval-augmented Q&A over indexed SEC filing chunks.

## Command

```bash
sec-nlp research ask [SYMBOL ...] --question "What changed in risk factors?"
```

If `--question` is omitted and `--interactive` is enabled (default), it starts an interactive terminal session.

## Core Flow

1. Query Qdrant collections (default: `retrieve`, `analyze`).
2. Apply optional symbol/form/date filters and reranking (`score` or `mmr`).
3. Build citations and optional external market/news context.
4. Market context is derived once per request via `build_market_context(...)` and rendered using a profile (`compact` or `standard`).
5. Generate an analyst-style answer with the configured LLM. The prompt requires a bottom-line judgment, supporting evidence, counterpoints or limits, and a confidence call.
6. Optionally autosave transcript outputs.

## Key Configuration

- Env prefix: `SEC_NLP_CHAT_`
- `collections` (default `retrieve_bge_m3`, `analyze`)
- `top_k`, `max_context_chunks`, `rerank_mode`
- `prefetch_retrieve` to auto-run retrieve indexing when collections are missing/sparse
- `llm.model_name` defaults to `llama3.2:3b` for stronger evidence synthesis
- `include_market_context`, `market_context_profile`, `include_news_context`
- `strict_citations` and `transcript_autosave`

## Shared Semantic Chunking

All presets expose `semantic_chunking.*` nested settings from `BasePipelineSettings`.
Semantic chunking defaults to disabled; explicitly enable it only with the `vector`
extra and an available embedding model. Local sentence/section chunking requires no AI service.

Common CLI overrides:
- `--semantic-chunking.enabled true`
- `--semantic-chunking.embedding-model qwen3-embedding:4b`
- `--semantic-chunking.breakpoint-threshold-type gradient`

Pipelines that chunk filing text directly (`retrieve`, `exb`, `warranty`, and loader-backed `analyze`) apply these settings during chunk generation. Other presets keep the same config surface for research configuration consistency.

## Outputs

Run-scoped path:

```text
outputs/<run_timestamp>/chat/<SYMBOL|ALL>/
```

Files:
- `<symbol>_chat_<run_id>_transcript.csv`
- `<symbol>_chat_<run_id>_summary.json`
- `<symbol>_chat_<run_id>_summary.yaml`

Output format is controlled by `output_format` (`csv`, `json`, `yaml`, `all`; default `all`).

## Source Pointers

- Config: `src/sec_nlp/pipelines/presets/chat/config.py`
- Pipeline: `src/sec_nlp/pipelines/presets/chat/pipeline.py`
- IO: `src/sec_nlp/pipelines/presets/chat/io/`
