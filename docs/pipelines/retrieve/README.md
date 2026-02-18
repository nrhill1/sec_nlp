# Retrieve Pipeline

`retrieve` runs an EFTS-first retrieval workflow and emits ranked filing hits.

## Command

```bash
sec-nlp retrieve AAPL --queries "pricing pressure" "supply chain"
```

You must provide at least one query.

## Core Flow

1. Candidate search via EFTS per query.
2. Rank and merge hits.
3. Optionally hydrate with downloaded chunks.
4. Optional embedding rerank and optional Qdrant indexing.
5. Write ranked summary artifacts.

## Key Configuration

- Env prefix: `SEC_NLP_RETRIEVE_`
- `queries` (required)
- `top_k`, `efts_candidates`
- `download_missing`, `max_chunks_per_accession`
- `rerank_with_embeddings`, `embedding_weight`
- `index_results` (persist snippets to Qdrant)
- `output_format` (default `json`)

## Outputs

```text
outputs/<run_timestamp>/retrieve/<SYMBOL|ALL>/
```

Files:
- `<symbol>_retrieve_<run_id>_ranked.csv`
- `<symbol>_retrieve_<run_id>_summary.json`
- `<symbol>_retrieve_<run_id>_summary.yaml`

## Source Pointers

- Config: `src/sec_nlp/pipelines/presets/retrieve/config.py`
- Pipeline: `src/sec_nlp/pipelines/presets/retrieve/pipeline.py`
- Steps: `src/sec_nlp/pipelines/presets/retrieve/steps/`
