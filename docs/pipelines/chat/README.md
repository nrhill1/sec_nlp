# Chat Pipeline

`chat` provides retrieval-augmented Q&A over indexed SEC filing chunks.

## Command

```bash
sec-nlp chat [SYMBOL ...] --question "What changed in risk factors?"
```

If `--question` is omitted and `--interactive` is enabled (default), it starts an interactive terminal session.

## Core Flow

1. Query Qdrant collections (default: `retrieve`, `analyze`).
2. Apply optional symbol/form/date filters and reranking (`score` or `mmr`).
3. Build citations and optional external market/news context.
4. Generate answer with the configured LLM.
5. Optionally autosave transcript outputs.

## Key Configuration

- Env prefix: `SEC_NLP_CHAT_`
- `collections` (default `retrieve`, `analyze`)
- `top_k`, `max_context_chunks`, `rerank_mode`
- `prefetch_retrieve` to auto-run retrieve indexing when collections are missing/sparse
- `include_market_context`, `include_news_context`
- `strict_citations` and `transcript_autosave`

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
