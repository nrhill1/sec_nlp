# Retrieve Pipeline

`retrieve` runs an EFTS-first retrieval workflow and emits ranked filing hits.

## Command

```bash
sec-nlp retrieve AAPL --queries "pricing pressure" "supply chain"
```

You must provide at least one query.

## Core Flow

1. Candidate search via EFTS per query.
2. Rank and merge hits across queries.
3. Apply lexical pruning gates (`query_term_min_hits`, `query_term_min_ratio`).
4. Optionally hydrate snippets from filing HTML (section-targeted or missing-snippet recovery).
5. Optional embedding rerank and optional Qdrant indexing.
6. Write run-scoped ranked artifacts.

## Snippet Behavior

- Primary source: EFTS snippet text from candidate hits.
- Hydration source: chunk extracted from filing HTML via `Loader.transform_html(...)`.
- Default behavior: hydration does **not** run for generic retrieval (`sections=[]` and `hydrate_missing_snippets=false`).
- Hydration runs when:
  - `sections` is set (section-targeted extraction), or
  - `hydrate_missing_snippets=true` and a hit lacks snippet text.
- `max_chunks_per_accession` is a cap for chunk scanning, not a target.

## Key Configuration

- Env prefix: `SEC_NLP_RETRIEVE_`
- `queries` (required)
- `top_k`, `efts_candidates`
- `hydrate_top_n` (caps how many ranked hits enter hydration stage)
- `query_term_min_hits`, `query_term_min_ratio`
- `stopword_aware_lexical` (default `true`; filters common stopwords for lexical matching)
- `sections` (enables section-targeted chunk extraction)
- `download_missing`, `max_chunks_per_accession`, `hydrate_missing_snippets`
- `rerank_with_embeddings`, `embedding_weight`
- `index_results` (persist snippets to Qdrant; default collection `retrieve_bge_m3`)
- default retrieve embedding model: `bge-m3`
- `output_format` (default `json`)

## Shared Semantic Chunking

All presets expose `semantic_chunking.*` nested settings from `BasePipelineSettings`.

Common CLI overrides:
- `--semantic-chunking.enabled true`
- `--semantic-chunking.embedding-model qwen3-embedding:4b`
- `--semantic-chunking.breakpoint-threshold-type gradient`
- `--semantic-chunking.max-chunk-tokens 384`

Pipelines that chunk filing text directly (`retrieve`, `exb`, `warranty`, and loader-backed `analyze`) apply these settings during chunk generation. Other presets keep the same config surface for CLI/flow consistency.

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
