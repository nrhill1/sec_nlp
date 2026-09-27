# Exhibit Pipeline (`exb`)

`exb` extracts exhibit content by category/number and exports source evidence.
Extraction works in the base installation without LangChain, embeddings, or Qdrant.
Indexing and semantic search are explicit options requiring the `vector` extra.
HTML extraction uses structured parsing when its local spaCy model is available,
and a logged local text fallback otherwise; it never installs model files.

## Command

```bash
sec-nlp research exb DE --exhibit-categories contracts subsidiaries consents
```

## Execution

Typed extraction steps execute sequentially through ordinary Python calls with
shared run identifiers. The terminal owns progress and cancellation. Settings
validation is separate from execution and does not create run records.

## Core Flow

1. Download filings and collect exhibit documents.
2. Pre-filter/chunk/dedupe exhibit text.
3. Optionally upload vectors to Qdrant.
4. Write exhibit index + summary artifacts.
5. Optionally run semantic search queries (`search.queries`).
6. Optional candidate-first mode can narrow processing to top EFTS accessions.

## Key Configuration

- Env prefix: `SEC_NLP_EXB_`
- `exhibit_categories` / `exhibit_numbers`
- `contract_categories` and `search_terms`
- `search_only` to skip indexing and query existing vectors
- `index_results` (default `false`) to explicitly enable vector indexing
- `dry_run` to skip vector upload after indexing is selected
- `export_format` (`yaml`, `json`, `csv`, `both`; default `yaml`)
- `candidate_first` to reuse retrieve EFTS/ranking logic for accession narrowing
- `candidate_queries`, `candidate_top_k`, `efts_candidates`
- `candidate_fallback_full_scan` for safe fallback when no candidate accessions are found

## Shared Semantic Chunking

All presets expose `semantic_chunking.*` nested settings from `BasePipelineSettings`.
Semantic chunking defaults to disabled; explicitly enable it only with the `vector`
extra and an available embedding model. Local sentence/section chunking requires no AI service.

Common CLI overrides:
- `--semantic-chunking.enabled true`
- `--semantic-chunking.embedding-model qwen3-embedding:4b`
- `--semantic-chunking.breakpoint-threshold-type gradient`
- `--semantic-chunking.max-chunk-tokens 384`

Pipelines that chunk filing text directly (`retrieve`, `exb`, `warranty`, and loader-backed `analyze`) apply these settings during chunk generation. Other presets keep the same config surface for research configuration consistency.

## Outputs

Main run-scoped path:

```text
outputs/<run_timestamp>/exhibit/<SYMBOL>/
```

Files:
- `<symbol>_exhibit_index_<run_id>.yaml|json|csv`
- `<symbol>_exhibit_summary_<run_id>.yaml|json`

Semantic search export path:

```text
outputs/search/<run_timestamp>/<query_slug>.yaml
```

## Source Pointers

- Config: `src/sec_nlp/pipelines/presets/exb/config.py`
- Pipeline: `src/sec_nlp/pipelines/presets/exb/pipeline.py`
- IO: `src/sec_nlp/pipelines/presets/exb/io/`
