# Exhibit Pipeline (`exb`)

`exb` extracts and indexes exhibit content by category/number with optional semantic search.

## Command

```bash
sec-nlp exb DE --exhibit-categories contracts subsidiaries consents
```

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
- `dry_run` to skip vector upload
- `export_format` (`yaml`, `json`, `csv`, `both`; default `yaml`)
- `candidate_first` to reuse retrieve EFTS/ranking logic for accession narrowing
- `candidate_queries`, `candidate_top_k`, `efts_candidates`
- `candidate_fallback_full_scan` for safe fallback when no candidate accessions are found

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
